"""
tests/test_search_fts.py

Regression tests for scripts/search_fts.py.

Uses an in-memory SQLite DB with the real schema.
Inserts tiny synthetic fixtures directly into cases/clusters/opinions/chunks.
Relies on real FTS triggers to keep chunks_fts in sync.
No live CourtListener calls. No real corpus dependency.
"""

import importlib.util
import io
import sqlite3
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SEARCH_PATH = REPO_ROOT / "scripts" / "search_fts.py"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def load_search_module():
    spec = importlib.util.spec_from_file_location("search_fts_under_test", SEARCH_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_conn() -> sqlite3.Connection:
    """In-memory DB initialized with the real schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def insert_search_fixture(
    conn: sqlite3.Connection,
    case_id: int,
    opinion_id: int,
    chunk_id: int,
    chunk_index: int,
    text: str,
    case_name: str = "Test Case",
    docket_number: str = "24-0001",
    source_docket_id: int = None,
    source_opinion_id: int = None,
) -> None:
    """
    Insert minimal rows for a single chunk, satisfying all FK constraints.
    FTS triggers on `chunks` will automatically populate `chunks_fts`.
    """
    sdid = source_docket_id or case_id * 1000
    soid = source_opinion_id or opinion_id

    conn.execute(
        """
        INSERT OR IGNORE INTO cases (
            id, source_docket_id, court_id, case_name, docket_number, date_ingested
        ) VALUES (?, ?, 'scotus', ?, ?, '2026-01-01')
        """,
        (case_id, sdid, case_name, docket_number),
    )
    cluster_id = opinion_id * 10
    conn.execute(
        """
        INSERT OR IGNORE INTO clusters (
            id, source_cluster_id, case_id, date_ingested
        ) VALUES (?, ?, ?, '2026-01-01')
        """,
        (cluster_id, cluster_id * 100, case_id),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO opinions (
            id, source_opinion_id, case_id, cluster_id,
            clean_text, text_source, date_ingested
        ) VALUES (?, ?, ?, ?, ?, 'plain_text', '2026-01-01')
        """,
        (opinion_id, soid, case_id, cluster_id, text),
    )
    conn.execute(
        """
        INSERT INTO chunks (
            id, opinion_id, case_id, chunk_index,
            text, char_start, char_end
        ) VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (chunk_id, opinion_id, case_id, chunk_index, text, len(text)),
    )


search = load_search_module()

# Re-usable SQL that mirrors search_fts.SEARCH_SQL but runs against a given conn
_SEARCH_SQL = search.SEARCH_SQL


def run_search(conn: sqlite3.Connection, query: str, limit: int = 10):
    """Execute SEARCH_SQL against a test connection directly."""
    return conn.execute(_SEARCH_SQL, (query, limit)).fetchall()


class TestSearchBasic(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()
        insert_search_fixture(
            self.conn,
            case_id=1,
            opinion_id=1,
            chunk_id=1,
            chunk_index=0,
            text="The doctrine of contributory liability applies here.",
            case_name="Sony v. Cox",
            docket_number="24-171",
            source_docket_id=71978744,
            source_opinion_id=11281536,
        )
        insert_search_fixture(
            self.conn,
            case_id=1,
            opinion_id=1,
            chunk_id=2,
            chunk_index=1,
            text="Vicarious liability requires direct financial benefit.",
        )
        insert_search_fixture(
            self.conn,
            case_id=2,
            opinion_id=2,
            chunk_id=3,
            chunk_index=0,
            text="Free speech protections are well established under the First Amendment.",
            case_name="Speech Case",
            docket_number="23-999",
            source_docket_id=99999,
            source_opinion_id=55555,
        )

    def tearDown(self):
        self.conn.close()

    # ── 1. Basic term query returns hits ──────────────────────────────────────

    def test_basic_term_returns_hits(self):
        rows = run_search(self.conn, "contributory")
        self.assertGreater(len(rows), 0)

    def test_basic_term_no_false_positives(self):
        """A term only in chunk 1 should not match chunk 3."""
        rows = run_search(self.conn, "contributory")
        texts = [r["snippet"] for r in rows]
        # None of the results should come from the speech chunk
        for r in rows:
            self.assertNotEqual(r["case_id"], 2)

    # ── 2. Quoted phrase query works ──────────────────────────────────────────

    def test_quoted_phrase_returns_hits(self):
        rows = run_search(self.conn, '"free speech"')
        self.assertGreater(len(rows), 0)

    def test_quoted_phrase_matches_correct_chunk(self):
        rows = run_search(self.conn, '"free speech"')
        self.assertEqual(rows[0]["case_id"], 2)

    # ── 3. Zero-result query behaves correctly ────────────────────────────────

    def test_absent_term_returns_zero_rows(self):
        rows = run_search(self.conn, "xylophone")
        self.assertEqual(len(rows), 0)

    def test_print_results_no_results_message(self):
        out = io.StringIO()
        with redirect_stdout(out):
            search.print_results("xylophone", [])
        output = out.getvalue()
        self.assertIn("No results found", output)
        self.assertIn("xylophone", output)
        self.assertNotIn("Hits:", output)

    # ── 4. Invalid FTS query is handled cleanly ───────────────────────────────

    def test_invalid_query_exits_with_friendly_error(self):
        """An unmatched quote is a malformed FTS5 query."""
        with patch.object(sys, "argv", ["search_fts.py", '"unmatched']):
            err = io.StringIO()
            with redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    # Patch get_connection to use our test conn
                    with patch.object(search, "get_connection", return_value=self.conn):
                        search.main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("invalid FTS query", err.getvalue())

    # ── 5. Result ordering is deterministic ──────────────────────────────────

    def test_ordering_by_score_then_chunk_id(self):
        """
        Both chunk 1 and chunk 2 belong to the same opinion.
        Results for a term present in both should be ordered by score ASC,
        then chunk_id ASC for ties.
        """
        insert_search_fixture(
            self.conn,
            case_id=1,
            opinion_id=1,
            chunk_id=4,
            chunk_index=2,
            text="liability liability liability",  # higher tf for 'liability'
        )
        rows = run_search(self.conn, "liability")
        self.assertGreater(len(rows), 0)
        # Verify score is non-decreasing (ASC)
        scores = [r["score"] for r in rows]
        self.assertEqual(scores, sorted(scores))
        # For any tied scores, chunk_id must be ascending
        for i in range(len(rows) - 1):
            if rows[i]["score"] == rows[i + 1]["score"]:
                self.assertLess(rows[i]["chunk_id"], rows[i + 1]["chunk_id"])

    # ── 6. Snippet is populated and highlights the query term ─────────────────

    def test_snippet_is_non_empty(self):
        rows = run_search(self.conn, "contributory")
        self.assertTrue(rows[0]["snippet"])

    def test_snippet_highlights_term(self):
        """snippet() uses '[' and ']' as highlight markers."""
        rows = run_search(self.conn, "contributory")
        snippet = rows[0]["snippet"]
        self.assertIn("[", snippet)
        self.assertIn("]", snippet)

    # ── 7. Traceability fields are present and correctly mapped ───────────────

    def test_traceability_fields(self):
        rows = run_search(self.conn, '"free speech"')
        self.assertEqual(len(rows), 1)
        row = rows[0]

        self.assertEqual(row["chunk_id"], 3)
        self.assertEqual(row["chunk_index"], 0)
        self.assertEqual(row["opinion_id"], 2)
        self.assertEqual(row["source_opinion_id"], 55555)
        self.assertEqual(row["case_id"], 2)
        self.assertEqual(row["source_docket_id"], 99999)
        self.assertEqual(row["case_name"], "Speech Case")
        self.assertEqual(row["docket_number"], "23-999")
        self.assertEqual(row["char_start"], 0)
        self.assertGreater(row["char_end"], 0)
        self.assertIsNotNone(row["score"])
        self.assertTrue(row["snippet"])

    # ── 8. Printed output includes traceability identifiers ───────────────────

    def test_print_results_includes_traceability_ids(self):
        rows = run_search(self.conn, '"free speech"')
        out = io.StringIO()
        with redirect_stdout(out):
            search.print_results("free speech", rows)
        output = out.getvalue()
        self.assertIn("chunk_id=3", output)
        self.assertIn("opinion_id=2", output)
        self.assertIn("case_id=2", output)
        self.assertIn("source_docket_id=99999", output)


if __name__ == "__main__":
    unittest.main()
