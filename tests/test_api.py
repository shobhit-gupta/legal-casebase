"""
tests/test_api.py

Tests for the legal casebase FastAPI endpoints:
  - GET /search
  - GET /stats
  - GET /cases/{case_id}

Patches app.main.search_casebase and app.main.get_connection so no
real DB or network calls are needed.
"""

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

FAKE_RESULT = {
    "chunk_id": 1,
    "chunk_index": 0,
    "opinion_id": 1,
    "source_opinion_id": 11111,
    "case_id": 1,
    "source_docket_id": 99999,
    "case_name": "Test v. Case",
    "docket_number": "24-001",
    "char_start": 0,
    "char_end": 42,
    "text": "The court held that.",
    "preview": "The court held that.",
    "snippet": None,
    "fts_score": None,
    "fts_rank": None,
    "vector_score": 0.9,
    "vector_rank": 1,
    "combined_score": 0.016,
    "matched_by": "vector",
}


class TestSearchEndpoint(unittest.TestCase):
    def test_successful_search(self):
        with patch(
            "app.main.search_casebase", return_value=[FAKE_RESULT]
        ) as mock_search:
            resp = client.get(
                "/search", params={"query": "copyright", "mode": "hybrid"}
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["query"], "copyright")
        self.assertEqual(body["mode"], "hybrid")
        self.assertEqual(body["count"], 1)
        self.assertEqual(len(body["results"]), 1)
        mock_search.assert_called_once_with(query="copyright", limit=10, mode="hybrid")
        self.assertEqual(body["results"][0]["chunk_id"], 1)

    def test_missing_query_returns_422(self):
        resp = client.get("/search")
        self.assertEqual(resp.status_code, 422)

    def test_invalid_limit_returns_400(self):
        with patch(
            "app.main.search_casebase",
            side_effect=ValueError("Limit must be > 0, got 0."),
        ):
            resp = client.get("/search", params={"query": "test", "limit": 0})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_mode_returns_400(self):
        with patch(
            "app.main.search_casebase", side_effect=ValueError("Invalid mode 'bad'")
        ):
            resp = client.get("/search", params={"query": "test", "mode": "bad"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())

    def test_empty_query_returns_400(self):
        with patch(
            "app.main.search_casebase",
            side_effect=ValueError("Query must not be empty"),
        ):
            resp = client.get("/search", params={"query": "   "})
        self.assertEqual(resp.status_code, 400)

    def test_fts_syntax_error_returns_400(self):
        with patch(
            "app.main.search_casebase",
            side_effect=RuntimeError("Invalid FTS query syntax: fts5: syntax error"),
        ):
            resp = client.get("/search", params={"query": '"unmatched'})
        self.assertEqual(resp.status_code, 400)

    def test_infrastructure_error_returns_500_with_generic_message(self):
        with patch(
            "app.main.search_casebase",
            side_effect=RuntimeError("OPENAI_API_KEY is not set."),
        ):
            resp = client.get("/search", params={"query": "test"})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["detail"], "Internal search error")


class TestStatsEndpoint(unittest.TestCase):
    def _mock_conn(self, counts=(10, 20, 30)):
        """
        Return a context-manager mock whose execute().fetchone()
        returns each count in sequence across the three COUNT queries.
        """
        mock_ctx = MagicMock()
        conn = mock_ctx.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.side_effect = [[c] for c in counts]
        return mock_ctx

    def test_stats_success_with_correct_counts(self):
        """DB counts are returned accurately and metadata fields are present."""
        with (
            patch("app.main.get_connection", self._mock_conn((10, 20, 30))),
            patch(
                "app.main._read_faiss_meta",
                return_value=("text-embedding-3-small", 1536),
            ),
        ):
            resp = client.get("/stats")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["cases"], 10)
        self.assertEqual(body["opinions"], 20)
        self.assertEqual(body["chunks_indexed"], 30)
        self.assertEqual(body["court"], "U.S. Supreme Court")
        self.assertEqual(body["source"], "CourtListener")
        self.assertEqual(body["retrieval_modes"], ["fts", "vector", "hybrid"])

    def test_stats_uses_faiss_meta_for_vector_fields(self):
        """embedding_model and vector_dimension come from _read_faiss_meta()."""
        with (
            patch("app.main.get_connection", self._mock_conn()),
            patch(
                "app.main._read_faiss_meta",
                return_value=("text-embedding-3-small", 1536),
            ) as mock_meta,
        ):
            resp = client.get("/stats")

        mock_meta.assert_called_once()
        body = resp.json()
        self.assertEqual(body["embedding_model"], "text-embedding-3-small")
        self.assertEqual(body["vector_dimension"], 1536)

    def test_stats_db_failure_returns_500(self):
        """If the DB is unavailable, /stats returns 500 with a generic message."""
        with patch("app.main.get_connection", side_effect=Exception("DB unavailable")):
            resp = client.get("/stats")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["detail"], "Internal server error")


class TestCaseDetailEndpoint(unittest.TestCase):
    def _mock_case_conn(self, case_row, opinion_rows, citation_rows):
        """
        Return a context-manager mock that serves fetchone() then two fetchall() calls
        in the order the endpoint issues them: case → opinions → citations.
        """
        mock_ctx = MagicMock()
        conn = mock_ctx.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = case_row
        conn.execute.return_value.fetchall.side_effect = [opinion_rows, citation_rows]
        return mock_ctx

    def test_case_detail_success(self):
        fake_case = {"id": 5, "case_name": "Test v. Case", "docket_number": "24-001"}
        fake_opinion = {"id": 1, "case_id": 5, "opinion_type": "010combined"}
        fake_citation = {"id": 1, "from_opinion_id": 1, "to_opinion_id": None}

        with patch(
            "app.main.get_connection",
            self._mock_case_conn(fake_case, [fake_opinion], [fake_citation]),
        ):
            resp = client.get("/cases/5")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # Top-level keys present
        for key in ("case", "opinions", "citations"):
            self.assertIn(key, body)
        # Actual values match the mocked data
        self.assertEqual(body["case"]["id"], 5)
        self.assertEqual(len(body["opinions"]), 1)
        self.assertEqual(len(body["citations"]), 1)
        self.assertEqual(body["opinions"][0]["opinion_type"], "010combined")

    def test_case_detail_not_found(self):
        with patch("app.main.get_connection") as mock_conn:
            conn = mock_conn.return_value.__enter__.return_value
            conn.execute.return_value.fetchone.return_value = None
            resp = client.get("/cases/9999")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"], "Case not found")

    def test_case_detail_db_failure_returns_500(self):
        with patch("app.main.get_connection", side_effect=Exception("DB error")):
            resp = client.get("/cases/1")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["detail"], "Internal server error")


if __name__ == "__main__":
    unittest.main()
