"""
scripts/chunk.py

Reads normalized opinions from SQLite and generates chunk rows.

Does NOT generate embeddings or touch FAISS.
Relies on the existing SQLite FTS5 triggers on `chunks` to keep
`chunks_fts` in sync automatically.

Usage:
    python scripts/chunk.py

Behavior:
    Full reset / rebuild. Clears all existing chunks and re-inserts
    from normalized opinions. Deterministic: opinions processed in
    source_opinion_id order.

Chunking strategy:
    Paragraph-first, span-based over clean_text.
    Section-aware chunking is deferred; section_hint = NULL for all chunks.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import get_connection

# ── Chunking constants ─────────────────────────────────────────────────────────

TARGET_CHARS = 1200  # soft stopping goal
HARD_MAX_CHARS = 1800  # hard ceiling — never exceeded
OVERLAP_CHARS = 200  # overlap between consecutive chunks

# Paragraph separator: blank line (with optional whitespace between newlines)
_PARA_SEP_RE = re.compile(r"\n\s*\n+")

# Sentence boundary: after .  !  ? followed by whitespace
_SENT_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


# ── Span utilities ─────────────────────────────────────────────────────────────


def paragraph_spans(text: str) -> list[tuple[int, int]]:
    """
    Return (start, end) spans of non-empty paragraphs in `text`.
    Paragraph boundaries are blank lines matching r'\\n\\s*\\n+'.
    """
    spans = []
    prev = 0
    for m in _PARA_SEP_RE.finditer(text):
        start, end = prev, m.start()
        if text[start:end].strip():
            spans.append((start, end))
        prev = m.end()
    # trailing paragraph after last separator
    if text[prev:].strip():
        spans.append((prev, len(text)))
    return spans


def subdivide_span(
    text: str,
    start: int,
    end: int,
    hard_max: int = HARD_MAX_CHARS,
) -> list[tuple[int, int]]:
    """
    Break a span that exceeds hard_max into smaller spans.

    First tries sentence boundaries directly in the original string (no offset
    drift). If any sentence span still exceeds hard_max, slices it by character.
    """
    if end - start <= hard_max:
        return [(start, end)]

    # Find sentence boundaries within the paragraph span
    matches = list(_SENT_BOUNDARY_RE.finditer(text, pos=start, endpos=end))
    positions = [start] + [m.end() for m in matches] + [end]
    sentence_spans = [
        (positions[i], positions[i + 1])
        for i in range(len(positions) - 1)
        if text[positions[i] : positions[i + 1]].strip()
    ]

    # Character-slice any sentence spans that still exceed hard_max
    result = []
    for s, e in sentence_spans:
        while e - s > hard_max:
            result.append((s, s + hard_max))
            s += hard_max
        if s < e:
            result.append((s, e))
    return result


def all_spans(text: str) -> list[tuple[int, int]]:
    """
    Produce a flat list of (start, end) spans covering `text`.
    Oversized paragraph spans are subdivided; all spans are ≤ HARD_MAX_CHARS.
    """
    spans = []
    for s, e in paragraph_spans(text):
        spans.extend(subdivide_span(text, s, e))
    return spans


# ── Chunking ───────────────────────────────────────────────────────────────────


def chunk_opinion(
    conn,
    opinion_id: int,
    case_id: int,
    clean_text: str,
    target: int = TARGET_CHARS,
    hard_max: int = HARD_MAX_CHARS,
    overlap: int = OVERLAP_CHARS,
) -> int:
    """
    Chunk a single opinion's clean_text and insert chunk rows.

    Returns the number of chunks inserted.
    Raises RuntimeError if a non-empty opinion produces zero chunks.
    """
    spans = all_spans(clean_text)
    if not spans:
        return 0

    chunk_index = 0

    def emit(char_start: int, char_end: int) -> None:
        nonlocal chunk_index
        # char_end is exclusive (Python slice semantics)
        if char_end - char_start > hard_max:
            raise RuntimeError(
                f"Opinion {opinion_id}: chunk [{char_start}:{char_end}] "
                f"size {char_end - char_start} exceeds HARD_MAX_CHARS ({hard_max}). "
                "Bug in chunking logic."
            )
        text = clean_text[char_start:char_end]
        if not text.strip():
            raise RuntimeError(
                f"Opinion {opinion_id}: span [{char_start}:{char_end}] "
                "produced empty chunk text — likely a bug in span generation."
            )
        conn.execute(
            """
            INSERT INTO chunks (
                opinion_id, case_id, chunk_index,
                section_hint, text, char_start, char_end, embedding_model
            ) VALUES (?, ?, ?, NULL, ?, ?, ?, NULL)
            """,
            (opinion_id, case_id, chunk_index, text, char_start, char_end),
        )
        chunk_index += 1

    def next_chunk_start(current_end: int, next_span_end: int) -> int:
        """
        Compute the start of the next chunk after emitting one ending at current_end.

        Backs up by OVERLAP_CHARS, but clamps so that the next span
        (ending at next_span_end) does not push the new chunk over HARD_MAX_CHARS.

        Note: overlap may begin mid-word or mid-sentence.
        Sentence-aligned overlap is a deferred improvement.
        """
        ideal = max(0, current_end - overlap)
        # Ensure next_span_end - chunk_start <= hard_max
        clamped = max(ideal, next_span_end - hard_max)
        return clamped

    chunk_start = spans[0][0]
    current_end = chunk_start  # nothing accumulated yet

    for s, e in spans:
        if current_end == chunk_start:
            # Nothing accumulated — accept, but clamp chunk_start if the span
            # alone would exceed hard_max (can happen after overlap backs us up)
            if e - chunk_start > hard_max:
                chunk_start = e - hard_max
            current_end = e
            if current_end - chunk_start >= target:
                emit(chunk_start, current_end)
                chunk_start = next_chunk_start(current_end, current_end)
                current_end = chunk_start

        elif (e - chunk_start) > hard_max:
            # Adding this span would breach the hard ceiling — emit first
            emit(chunk_start, current_end)
            chunk_start = next_chunk_start(current_end, e)
            current_end = e
            # Do not check TARGET here: this span was forced into a new chunk

        else:
            # Adding stays under hard ceiling — accept
            current_end = e
            if current_end - chunk_start >= target:
                emit(chunk_start, current_end)
                chunk_start = next_chunk_start(current_end, current_end)
                current_end = chunk_start

    # Emit any remaining accumulation
    if current_end > chunk_start:
        emit(chunk_start, current_end)

    return chunk_index


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    print("\nChunking opinions...\n")

    with get_connection() as conn:
        # Full reset — FTS5 triggers on chunks keep chunks_fts in sync
        print("Clearing existing chunks...")
        conn.execute("DELETE FROM chunks")
        print("  Done.\n")

        opinions = conn.execute(
            """
            SELECT id, case_id, source_opinion_id, clean_text
            FROM opinions
            ORDER BY source_opinion_id
            """
        ).fetchall()

        print(f"Processing {len(opinions)} opinions...\n")

        total_chunks = 0
        skipped = 0

        for opinion in opinions:
            opinion_id = opinion["id"]
            case_id = opinion["case_id"]
            source_id = opinion["source_opinion_id"]
            clean_text = opinion["clean_text"] or ""

            if not clean_text.strip():
                print(f"  [skip] opinion {source_id}: empty clean_text")
                skipped += 1
                continue

            count = chunk_opinion(conn, opinion_id, case_id, clean_text)

            if count == 0:
                raise RuntimeError(
                    f"Opinion {source_id} (id={opinion_id}) produced zero chunks "
                    "from non-empty clean_text."
                )

            total_chunks += count

        print(
            f"\nDone. {len(opinions) - skipped} opinions chunked, "
            f"{skipped} skipped, {total_chunks} chunks inserted."
        )


if __name__ == "__main__":
    main()
