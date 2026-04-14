"""
tests/test_chunk.py

Unit tests for scripts/chunk.py.

Uses a temporary in-memory SQLite DB initialized with the real db/schema.sql.
Synthetic opinion rows are inserted directly — no raw JSON, no CourtListener.

Covers:
1. Paragraph-first chunking on a small opinion
2. Overlap is applied across multiple chunks
3. No emitted chunk exceeds HARD_MAX_CHARS
4. Oversized paragraph is subdivided and still chunks successfully
5. Empty clean_text is skipped at the rebuild level (via main() path)
6. Non-empty text cannot silently yield zero chunks
7. FTS sync works through real schema triggers
"""

import importlib.util
import io
import sqlite3
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK_PATH = REPO_ROOT / "scripts" / "chunk.py"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def load_chunk_module():
    spec = importlib.util.spec_from_file_location("chunk_under_test", CHUNK_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_conn() -> sqlite3.Connection:
    """Open an in-memory SQLite DB initialized with the real schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def insert_opinion(conn, opinion_id: int, case_id: int, clean_text: str) -> None:
    """
    Insert the minimal rows needed to satisfy FK constraints for an opinion.
    Inserts a synthetic case and cluster if they don't exist yet.
    """
    # Insert case if not present
    exists = conn.execute(
        "SELECT 1 FROM cases WHERE id = ?", (case_id,)
    ).fetchone()
    if not exists:
        conn.execute(
            """
            INSERT INTO cases (
                id, source_docket_id, court_id, case_name, date_ingested
            ) VALUES (?, ?, 'scotus', 'Test Case', '2026-01-01')
            """,
            (case_id, case_id * 1000),
        )

    # Insert a synthetic cluster linked to this case
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
        INSERT INTO opinions (
            id, source_opinion_id, case_id, cluster_id,
            clean_text, text_source, date_ingested
        ) VALUES (?, ?, ?, ?, ?, 'plain_text', '2026-01-01')
        """,
        (opinion_id, opinion_id, case_id, cluster_id, clean_text),
    )


def run_quietly(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


chunk = load_chunk_module()


class TestChunkOpinion(unittest.TestCase):
    """Tests for chunk_opinion() directly."""

    def setUp(self):
        self.conn = make_conn()

    def tearDown(self):
        self.conn.close()

    def chunks_for(self, opinion_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM chunks WHERE opinion_id = ? ORDER BY chunk_index",
            (opinion_id,),
        ).fetchall()

    # ── 1. Paragraph-first chunking ───────────────────────────────────────────

    def test_paragraph_first_small_opinion(self):
        """Three short paragraphs all fit in one chunk."""
        text = "Para one.\n\nPara two.\n\nPara three."
        insert_opinion(self.conn, opinion_id=1, case_id=1, clean_text=text)

        count = run_quietly(chunk.chunk_opinion, self.conn, 1, 1, text)

        self.assertEqual(count, 1)
        rows = self.chunks_for(1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["chunk_index"], 0)
        self.assertIn("Para one", rows[0]["text"])
        self.assertIn("Para three", rows[0]["text"])
        self.assertIsNone(rows[0]["section_hint"])
        self.assertIsNone(rows[0]["embedding_model"])

    def test_char_start_and_end_are_correct_slices(self):
        """char_start and char_end slice back to chunk text exactly."""
        text = "Alpha.\n\nBeta.\n\nGamma."
        insert_opinion(self.conn, opinion_id=2, case_id=1, clean_text=text)
        run_quietly(chunk.chunk_opinion, self.conn, 2, 1, text)

        for row in self.chunks_for(2):
            sliced = text[row["char_start"]:row["char_end"]]
            self.assertEqual(sliced, row["text"])

    # ── 2. Overlap across chunks ──────────────────────────────────────────────

    def test_overlap_applied_across_chunks(self):
        """
        Three ~700-char paragraphs reliably force at least two chunks
        (total ~2100 chars, well above TARGET and HARD_MAX).
        Second chunk should start before first chunk ends by at most OVERLAP_CHARS.
        """
        para = "x" * 700
        text = para + "\n\n" + para + "\n\n" + para
        insert_opinion(self.conn, opinion_id=3, case_id=1, clean_text=text)

        count = run_quietly(chunk.chunk_opinion, self.conn, 3, 1, text)

        self.assertGreaterEqual(count, 2)
        rows = self.chunks_for(3)
        self.assertGreaterEqual(len(rows), 2)
        first_end = rows[0]["char_end"]
        second_start = rows[1]["char_start"]
        # Overlap: second chunk starts before first chunk ends
        self.assertLess(second_start, first_end)
        # Overlap must not exceed OVERLAP_CHARS
        self.assertLessEqual(first_end - second_start, chunk.OVERLAP_CHARS)

    # ── 3. No chunk exceeds HARD_MAX_CHARS ────────────────────────────────────

    def test_no_chunk_exceeds_hard_max(self):
        """All chunks must be within the hard ceiling."""
        # Build several medium paragraphs
        para = "The court held that. " * 40   # ~840 chars each
        text = ("\n\n".join([para] * 5))
        insert_opinion(self.conn, opinion_id=4, case_id=1, clean_text=text)
        run_quietly(chunk.chunk_opinion, self.conn, 4, 1, text)

        for row in self.chunks_for(4):
            size = row["char_end"] - row["char_start"]
            self.assertLessEqual(
                size,
                chunk.HARD_MAX_CHARS,
                f"Chunk {row['chunk_index']} size {size} exceeds HARD_MAX_CHARS",
            )

    # ── 4. Oversized paragraph is subdivided ──────────────────────────────────

    def test_oversized_paragraph_is_subdivided(self):
        """A single paragraph exceeding HARD_MAX_CHARS must still chunk cleanly."""
        # One paragraph of 3000 chars — well above HARD_MAX (1800)
        text = "The court held so. " * 160   # ~3040 chars, no double newlines
        insert_opinion(self.conn, opinion_id=5, case_id=1, clean_text=text)

        count = run_quietly(chunk.chunk_opinion, self.conn, 5, 1, text)

        self.assertGreaterEqual(count, 2)
        for row in self.chunks_for(5):
            size = row["char_end"] - row["char_start"]
            self.assertLessEqual(size, chunk.HARD_MAX_CHARS)

    # ── 6. Non-empty text cannot yield zero chunks ────────────────────────────

    def test_non_empty_text_always_yields_chunks(self):
        """chunk_opinion must never return 0 for non-empty text."""
        text = "A single short paragraph."
        insert_opinion(self.conn, opinion_id=6, case_id=1, clean_text=text)
        count = run_quietly(chunk.chunk_opinion, self.conn, 6, 1, text)
        self.assertGreater(count, 0)


class TestChunkRebuild(unittest.TestCase):
    """Tests for the full rebuild path (main() / DELETE + re-insert)."""

    def setUp(self):
        self.conn = make_conn()

    def tearDown(self):
        self.conn.close()

    def _run_main_with_conn(self):
        """
        Run the rebuild loop directly using our test connection,
        mirroring what main() does without opening a new connection.
        """
        opinions = self.conn.execute(
            """
            SELECT id, case_id, source_opinion_id, clean_text
            FROM opinions
            ORDER BY source_opinion_id
            """
        ).fetchall()

        self.conn.execute("DELETE FROM chunks")
        total = 0
        skipped = 0

        for op in opinions:
            clean_text = op["clean_text"] or ""
            if not clean_text.strip():
                skipped += 1
                continue
            count = chunk.chunk_opinion(
                self.conn, op["id"], op["case_id"], clean_text
            )
            if count == 0:
                raise RuntimeError(
                    f"Opinion {op['source_opinion_id']} yielded zero chunks."
                )
            total += count

        return total, skipped

    # ── 5. Empty clean_text is skipped ────────────────────────────────────────

    def test_empty_clean_text_is_skipped(self):
        """Opinions with empty clean_text produce no chunks and are counted as skipped."""
        insert_opinion(self.conn, opinion_id=10, case_id=2, clean_text="   ")
        insert_opinion(self.conn, opinion_id=11, case_id=2, clean_text="Real content here.")

        total, skipped = run_quietly(self._run_main_with_conn)

        self.assertEqual(skipped, 1)
        self.assertGreater(total, 0)
        # No chunks for opinion 10
        empty_chunks = self.conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE opinion_id = 10"
        ).fetchone()[0]
        self.assertEqual(empty_chunks, 0)

    # ── 7. FTS sync via triggers ──────────────────────────────────────────────

    def test_fts_sync_via_triggers(self):
        """
        Inserting chunks through chunk_opinion must keep chunks_fts in sync.
        A MATCH query on a word present in the chunk text must return rows.
        """
        text = "The doctrine of stare decisis requires consistency.\n\nCourts follow precedent."
        insert_opinion(self.conn, opinion_id=20, case_id=3, clean_text=text)

        run_quietly(chunk.chunk_opinion, self.conn, 20, 3, text)

        # FTS MATCH query — must return at least one result
        results = self.conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'stare'"
        ).fetchall()
        self.assertGreater(len(results), 0)

    def test_fts_delete_sync(self):
        """
        Deleting from chunks must also remove entries from chunks_fts.
        """
        text = "Unique canary word: xylophone."
        insert_opinion(self.conn, opinion_id=21, case_id=3, clean_text=text)
        run_quietly(chunk.chunk_opinion, self.conn, 21, 3, text)

        # Confirm it's in FTS
        before = self.conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'xylophone'"
        ).fetchall()
        self.assertGreater(len(before), 0)

        # Delete the chunk rows
        self.conn.execute("DELETE FROM chunks WHERE opinion_id = 21")

        # FTS should now return nothing
        after = self.conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'xylophone'"
        ).fetchall()
        self.assertEqual(len(after), 0)


if __name__ == "__main__":
    unittest.main()
