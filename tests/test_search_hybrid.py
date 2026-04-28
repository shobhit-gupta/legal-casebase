"""
tests/test_search_hybrid.py

Regression tests for scripts/search_hybrid.py.

Uses an in-memory SQLite DB with the real schema.
Inserts tiny synthetic fixtures into cases/clusters/opinions/chunks.
Relies on real FTS triggers for the FTS side.
Stubs the vector side (load_vector_artifacts, run_vector, OpenAI).
No live OpenAI calls. No real FAISS artifacts.
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
HYBRID_PATH = REPO_ROOT / "scripts" / "search_hybrid.py"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def load_hybrid_module():
    spec = importlib.util.spec_from_file_location("search_hybrid_under_test", HYBRID_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def insert_fixture(
    conn: sqlite3.Connection,
    chunk_id: int,
    text: str,
    case_id: int = 1,
    opinion_id: int = 1,
    chunk_index: int = 0,
    case_name: str = "Test Case",
    docket_number: str = "24-0001",
    source_docket_id: int = 9001,
    source_opinion_id: int = 8001,
) -> None:
    """Insert minimal FK-satisfying rows for one chunk. FTS triggers populate chunks_fts."""
    conn.execute(
        "INSERT OR IGNORE INTO cases "
        "(id, source_docket_id, court_id, case_name, docket_number, date_ingested) "
        "VALUES (?, ?, 'scotus', ?, ?, '2026-01-01')",
        (case_id, source_docket_id, case_name, docket_number),
    )
    cluster_id = opinion_id * 10
    conn.execute(
        "INSERT OR IGNORE INTO clusters "
        "(id, source_cluster_id, case_id, date_ingested) VALUES (?, ?, ?, '2026-01-01')",
        (cluster_id, cluster_id * 100, case_id),
    )
    conn.execute(
        "INSERT OR IGNORE INTO opinions "
        "(id, source_opinion_id, case_id, cluster_id, clean_text, text_source, date_ingested) "
        "VALUES (?, ?, ?, ?, ?, 'plain_text', '2026-01-01')",
        (opinion_id, source_opinion_id, case_id, cluster_id, text),
    )
    conn.execute(
        "INSERT INTO chunks "
        "(id, opinion_id, case_id, chunk_index, text, char_start, char_end) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (chunk_id, opinion_id, case_id, chunk_index, text, len(text)),
    )


def _make_vec_row(
    chunk_id: int, vector_rank: int, vector_score: float,
    case_id: int = 1, opinion_id: int = None, chunk_index: int = 0,
    source_opinion_id: int = None, source_docket_id: int = 9001,
    case_name: str = "Case", docket_number: str = "24-001",
    char_start: int = 0, char_end: int = None, text: str = "hello world",
) -> dict:
    """Build a minimal vector-result dict as run_vector() would return.
    Defaults aligned with _fts_row() so the same chunk_id works in both sources."""
    return {
        "chunk_id": chunk_id, "chunk_index": chunk_index,
        "opinion_id": opinion_id if opinion_id is not None else chunk_id,
        "source_opinion_id": source_opinion_id if source_opinion_id is not None else chunk_id * 100,
        "case_id": case_id, "source_docket_id": source_docket_id,
        "case_name": case_name, "docket_number": docket_number,
        "char_start": char_start,
        "char_end": char_end if char_end is not None else len(text),
        "text": text, "vector_score": vector_score, "vector_rank": vector_rank,
    }


hybrid = load_hybrid_module()
RRF_K      = hybrid.RRF_K
FTS_WEIGHT = hybrid.FTS_WEIGHT
VEC_WEIGHT = hybrid.VECTOR_WEIGHT


class TestMergeRRF(unittest.TestCase):
    """Direct tests of merge_rrf() — no DB, no network."""

    def _fts_row(self, chunk_id, rank, score=-1.0, text="hello world"):
        return {
            "chunk_id": chunk_id, "chunk_index": 0,
            "opinion_id": chunk_id, "source_opinion_id": chunk_id * 100,
            "case_id": 1, "source_docket_id": 9001,
            "case_name": "Case", "docket_number": "24-001",
            "char_start": 0, "char_end": len(text), "text": text,
            "fts_score": score, "fts_rank": rank,
        }

    def _vec_row(self, chunk_id, rank, score=0.9, text="hello world"):
        return _make_vec_row(
            chunk_id=chunk_id, vector_rank=rank, vector_score=score,
            char_end=len(text), text=text,
        )

    # ── 1. Overlap: matched_by="both" and correct combined score ─────────────

    def test_overlap_matched_by_both(self):
        fts = [self._fts_row(1, rank=1), self._fts_row(2, rank=2)]
        vec = [self._vec_row(1, rank=1), self._vec_row(3, rank=2)]
        result = hybrid.merge_rrf(fts, vec)
        by_id = {r["chunk_id"]: r for r in result}

        self.assertEqual(by_id[1]["matched_by"], "both")
        self.assertEqual(by_id[2]["matched_by"], "fts")
        self.assertEqual(by_id[3]["matched_by"], "vector")

    def test_overlap_combined_score_both(self):
        fts = [self._fts_row(1, rank=2)]
        vec = [self._vec_row(1, rank=3)]
        result = hybrid.merge_rrf(fts, vec)
        expected = FTS_WEIGHT / (RRF_K + 2) + VEC_WEIGHT / (RRF_K + 3)
        self.assertAlmostEqual(result[0]["combined_score"], expected, places=10)

    # ── 2. Single-source matched_by ───────────────────────────────────────────

    def test_fts_only_matched_by(self):
        fts = [self._fts_row(10, rank=1)]
        result = hybrid.merge_rrf(fts, [])
        self.assertEqual(result[0]["matched_by"], "fts")
        self.assertIsNone(result[0]["vector_rank"])
        self.assertIsNone(result[0]["vector_score"])

    def test_vector_only_matched_by(self):
        vec = [self._vec_row(20, rank=1)]
        result = hybrid.merge_rrf([], vec)
        self.assertEqual(result[0]["matched_by"], "vector")
        self.assertIsNone(result[0]["fts_rank"])
        self.assertIsNone(result[0]["fts_score"])

    # ── 3. RRF formula correctness ────────────────────────────────────────────

    def test_rrf_fts_only_score(self):
        fts = [self._fts_row(1, rank=5)]
        result = hybrid.merge_rrf(fts, [])
        expected = FTS_WEIGHT / (RRF_K + 5)
        self.assertAlmostEqual(result[0]["combined_score"], expected, places=10)

    def test_rrf_vector_only_score(self):
        vec = [self._vec_row(1, rank=7)]
        result = hybrid.merge_rrf([], vec)
        expected = VEC_WEIGHT / (RRF_K + 7)
        self.assertAlmostEqual(result[0]["combined_score"], expected, places=10)

    def test_rrf_missing_rank_contributes_zero(self):
        fts = [self._fts_row(1, rank=1)]
        vec = [self._vec_row(1, rank=1)]
        both = hybrid.merge_rrf(fts, vec)
        fts_only = hybrid.merge_rrf(fts, [])
        # combined must be strictly greater than fts-only
        self.assertGreater(both[0]["combined_score"], fts_only[0]["combined_score"])

    # ── 4. Sort order ──────────────────────────────────────────────────────────

    def test_sort_combined_score_descending(self):
        fts = [self._fts_row(1, rank=1), self._fts_row(2, rank=10)]
        result = hybrid.merge_rrf(fts, [])
        scores = [r["combined_score"] for r in result]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_sort_both_before_single(self):
        """
        Isolate the second sort key: 'both' before single-source.

        Construct genuinely equal combined scores:
          both row:     fts_rank=100, vec_rank=100
            → 1/(60+100) + 1/(60+100) = 1/160 + 1/160 = 0.0125
          fts-only row: fts_rank=20
            → 1/(60+20) = 1/80 = 0.0125

        Equal scores confirmed by assertAlmostEqual — the tiebreak,
        not score dominance, must drive the ordering.
        """
        fts = [self._fts_row(1, rank=100), self._fts_row(2, rank=20)]
        vec = [self._vec_row(1, rank=100)]
        result = hybrid.merge_rrf(fts, vec)
        by_id = {r["chunk_id"]: r for r in result}

        self.assertAlmostEqual(
            by_id[1]["combined_score"], by_id[2]["combined_score"], places=10
        )
        self.assertEqual(result[0]["chunk_id"], 1)
        self.assertEqual(result[0]["matched_by"], "both")

    def test_sort_best_rank_ascending_within_tied_scores(self):
        """
        Isolate the third sort key: best available rank ascending.

        Two 'both' rows with equal combined scores but different best ranks:
          row A: fts_rank=2,  vec_rank=126  → 1/(62) + 1/(186)
          row B: fts_rank=33, vec_rank=33   → 1/(93) + 1/(93)

        With RRF_K=60 both ≈ 0.02151...
        row A best_rank=2, row B best_rank=33.

        chunk_id=3 for row B and chunk_id=9 for row A — so chunk_id order
        alone would put B first. The rank tiebreak must put A first instead.
        """
        row_a_fts = self._fts_row(9, rank=2)
        row_a_vec = self._vec_row(9, rank=126)
        row_b_fts = self._fts_row(3, rank=33)
        row_b_vec = self._vec_row(3, rank=33)

        result = hybrid.merge_rrf(
            [row_a_fts, row_b_fts],
            [row_a_vec, row_b_vec],
        )
        by_id = {r["chunk_id"]: r for r in result}

        self.assertAlmostEqual(
            by_id[9]["combined_score"], by_id[3]["combined_score"], places=10
        )
        self.assertEqual(by_id[9]["matched_by"], "both")
        self.assertEqual(by_id[3]["matched_by"], "both")
        # row A (chunk 9, best_rank=2) must sort before row B (chunk 3, best_rank=33)
        self.assertEqual(result[0]["chunk_id"], 9)

    # ── 5. Metadata mismatch raises ───────────────────────────────────────────

    def test_metadata_mismatch_raises(self):
        fts = [self._fts_row(1, rank=1, text="original text")]
        vec = [self._vec_row(1, rank=1, text="different text")]
        with self.assertRaises(RuntimeError):
            hybrid.merge_rrf(fts, vec)

    def test_text_field_in_mismatch_check(self):
        """text is now part of _CHUNK_META_FIELDS — mismatch on text must raise."""
        self.assertIn("text", hybrid._CHUNK_META_FIELDS)


class TestFTSRetrieval(unittest.TestCase):
    """Tests for run_fts() against a real in-memory SQLite DB."""

    def setUp(self):
        self.conn = make_conn()
        insert_fixture(self.conn, chunk_id=1, text="contributory liability doctrine applies")
        insert_fixture(self.conn, chunk_id=2, text="free exercise of religion protected", opinion_id=2, source_opinion_id=8002)

    def tearDown(self):
        self.conn.close()

    def test_fts_returns_matching_chunk(self):
        rows = hybrid.run_fts(self.conn, "contributory")
        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[0]["chunk_id"], 1)

    def test_fts_ranks_are_1based(self):
        rows = hybrid.run_fts(self.conn, "contributory OR religion")
        ranks = [r["fts_rank"] for r in rows]
        self.assertIn(1, ranks)

    # ── 6. Invalid FTS query handling ────────────────────────────────────────

    def test_invalid_fts_query_exits(self):
        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                hybrid.run_fts(self.conn, '"unmatched')
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("invalid FTS query", err.getvalue())


class TestMainBehavior(unittest.TestCase):
    """Tests for main() via patched environment."""

    def setUp(self):
        self.conn = make_conn()
        insert_fixture(
            self.conn, chunk_id=1, text="stare decisis requires consistency",
            case_name="Test v. Case", docket_number="24-999",
            source_docket_id=7777, source_opinion_id=5555,
        )

    def tearDown(self):
        self.conn.close()

    def _stub_vec_row(self):
        return _make_vec_row(
            chunk_id=1, vector_rank=1, vector_score=0.9,
            case_name="Test v. Case", docket_number="24-999",
            source_docket_id=7777, source_opinion_id=5555,
            text="stare decisis requires consistency",
            char_end=len("stare decisis requires consistency"),
        )

    # ── 7. FTS syntax surfaces before vector prerequisites ───────────────────

    def test_fts_error_before_api_key_check(self):
        """With a bad FTS query and no API key, the FTS error surfaces first."""
        err = io.StringIO()
        env_without_key = {"OPENAI_API_KEY": ""}
        with patch.dict("os.environ", env_without_key):
            with patch.object(sys, "argv", ["search_hybrid.py", '"unmatched']):
                with patch.object(hybrid, "get_connection", return_value=self.conn):
                    with redirect_stderr(err):
                        with self.assertRaises(SystemExit) as cm:
                            hybrid.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("invalid FTS query", err.getvalue())
        # Must NOT reach the API key check
        self.assertNotIn("OPENAI_API_KEY", err.getvalue())

    # ── 8. Zero-results behavior ─────────────────────────────────────────────

    def test_zero_results_message(self):
        out = io.StringIO()
        with redirect_stdout(out):
            hybrid.print_results("xylophone", [])
        self.assertIn("No results found", out.getvalue())
        self.assertIn("xylophone", out.getvalue())

    # ── 9. Printed output includes traceability fields ───────────────────────

    def test_output_includes_traceability_fields(self):
        TEXT = "stare decisis requires consistency"
        merged = hybrid.merge_rrf(
            [{
                "chunk_id": 1, "chunk_index": 0,
                "opinion_id": 1, "source_opinion_id": 5555,
                "case_id": 1, "source_docket_id": 7777,
                "case_name": "Test v. Case", "docket_number": "24-999",
                "char_start": 0, "char_end": len(TEXT),
                "text": TEXT,
                "fts_score": -2.5, "fts_rank": 1,
            }],
            [self._stub_vec_row()],
        )
        out = io.StringIO()
        with redirect_stdout(out):
            hybrid.print_results("stare decisis", merged[:5])
        output = out.getvalue()

        for field in (
            "both", "combined", "fts_rank", "vec_rank",
            "fts_score", "vec_score",
            "chunk_id", "opinion_id", "case_id", "source_docket_id",
        ):
            self.assertIn(field, output, f"Expected '{field}' in output")


    # ── 10. Happy-path main() success ────────────────────────────────────────

    def test_main_happy_path(self):
        """main() completes successfully with stubbed vector side."""
        stub_vec_row = self._stub_vec_row()

        out = io.StringIO()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            with patch.object(sys, "argv", ["search_hybrid.py", "stare decisis"]):
                with patch.object(hybrid, "get_connection", return_value=self.conn):
                    with patch.object(hybrid, "load_vector_artifacts",
                                      return_value=({}, None, None)):
                        with patch.object(hybrid, "run_vector",
                                          return_value=[stub_vec_row]):
                            with redirect_stdout(out):
                                hybrid.main()

        output = out.getvalue()
        # Must have at least one hit
        self.assertIn("Hits:", output)
        self.assertNotIn("No results found", output)
        # Traceability fields present
        for field in ("both", "combined", "fts_rank", "vec_rank",
                      "chunk_id", "opinion_id", "case_id", "source_docket_id"):
            self.assertIn(field, output, f"Expected '{field}' in output")


if __name__ == "__main__":
    unittest.main()
