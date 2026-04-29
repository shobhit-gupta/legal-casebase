"""
tests/test_api.py

Minimal tests for the FastAPI search endpoint.
Patches app.main.search_casebase so no real DB or network is needed.
"""

import unittest
from unittest.mock import patch

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
        # Verify search_casebase was called with the expected arguments
        mock_search.assert_called_once_with(query="copyright", limit=10, mode="hybrid")
        # Spot-check one stable field in results
        self.assertEqual(body["results"][0]["chunk_id"], 1)

    def test_missing_query_returns_422(self):
        # No patch — testing framework-level required-parameter enforcement.
        # query is required at the FastAPI layer; missing it must return 422.
        resp = client.get("/search")
        self.assertEqual(resp.status_code, 422)

    def test_invalid_limit_returns_400(self):
        # limit=0 must reach retrieval and surface as 400 via ValueError,
        # not be rejected by FastAPI as 422.
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
        # Internal error detail must be hidden from the client
        self.assertEqual(resp.json()["detail"], "Internal search error")


if __name__ == "__main__":
    unittest.main()
