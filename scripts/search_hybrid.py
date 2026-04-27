"""
scripts/search_hybrid.py

Hybrid retrieval combining FTS keyword search and vector similarity search
using weighted Reciprocal Rank Fusion (RRF).

Both retrieval paths are required. This is a smoke-test / reference script,
not final product integration.

Usage:
    python scripts/search_hybrid.py "query string" [--limit N]
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

import faiss
import numpy as np
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import get_connection

# ── Constants ──────────────────────────────────────────────────────────────────

FTS_CANDIDATES    = 20
VECTOR_CANDIDATES = 20
RRF_K             = 60
FTS_WEIGHT        = 1.0
VECTOR_WEIGHT     = 1.0
EMBEDDING_MODEL   = "text-embedding-3-small"
PREVIEW_CHARS     = 220

FAISS_DIR  = ROOT / "storage" / "faiss"
INDEX_PATH = FAISS_DIR / "chunks.index"
IDS_PATH   = FAISS_DIR / "chunks_ids.npy"
META_PATH  = FAISS_DIR / "chunks_meta.json"

# ── Metadata fields that must agree when the same chunk appears in both sources
_CHUNK_META_FIELDS = (
    "chunk_index", "opinion_id", "source_opinion_id",
    "case_id", "source_docket_id", "case_name",
    "docket_number", "char_start", "char_end", "text",
)

# ── SQL ────────────────────────────────────────────────────────────────────────

FTS_SQL = """
SELECT
    c.id            AS chunk_id,
    c.chunk_index,
    c.opinion_id,
    o.source_opinion_id,
    c.case_id,
    cs.source_docket_id,
    cs.case_name,
    cs.docket_number,
    c.char_start,
    c.char_end,
    c.text,
    bm25(chunks_fts) AS fts_score
FROM chunks_fts
JOIN chunks   c  ON c.id = chunks_fts.rowid
JOIN opinions o  ON o.id = c.opinion_id
JOIN cases    cs ON cs.id = c.case_id
WHERE chunks_fts MATCH ?
ORDER BY fts_score ASC, c.id ASC
LIMIT ?
"""

VECTOR_META_SQL = """
SELECT
    c.id            AS chunk_id,
    c.chunk_index,
    c.opinion_id,
    o.source_opinion_id,
    c.case_id,
    cs.source_docket_id,
    cs.case_name,
    cs.docket_number,
    c.char_start,
    c.char_end,
    c.text
FROM chunks   c
JOIN opinions o  ON o.id = c.opinion_id
JOIN cases    cs ON cs.id = c.case_id
WHERE c.id IN ({placeholders})
"""

# ── Text utilities ─────────────────────────────────────────────────────────────

_WS_RE = re.compile(r"\s+")


def make_preview(text: str, max_chars: int = PREVIEW_CHARS) -> str:
    normalized = _WS_RE.sub(" ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars] + "…"


# ── FTS retrieval ──────────────────────────────────────────────────────────────

def run_fts(conn: sqlite3.Connection, query: str) -> list[dict]:
    """
    Run FTS retrieval. Returns rows with fts_rank (1-based) and fts_score.
    Fails clearly on invalid FTS query syntax.
    """
    try:
        rows = conn.execute(FTS_SQL, (query, FTS_CANDIDATES)).fetchall()
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        if any(kw in msg for kw in ("fts5", "match", "syntax", "unterminated string", "parse error", "malformed")):
            print(f"Error: invalid FTS query — {e}", file=sys.stderr)
            print(
                "Hint: multi-word queries must be quoted at the shell level.\n"
                "      Trailing wildcards work (copy*); leading wildcards do not.",
                file=sys.stderr,
            )
            sys.exit(1)
        raise

    results = []
    for rank, row in enumerate(rows, start=1):
        results.append({
            "chunk_id":          row["chunk_id"],
            "chunk_index":       row["chunk_index"],
            "opinion_id":        row["opinion_id"],
            "source_opinion_id": row["source_opinion_id"],
            "case_id":           row["case_id"],
            "source_docket_id":  row["source_docket_id"],
            "case_name":         row["case_name"],
            "docket_number":     row["docket_number"],
            "char_start":        row["char_start"],
            "char_end":          row["char_end"],
            "text":              row["text"],
            "fts_score":         row["fts_score"],
            "fts_rank":          rank,
        })
    return results


# ── Vector retrieval ───────────────────────────────────────────────────────────

def load_vector_artifacts() -> tuple[dict, np.ndarray, faiss.Index]:
    """Load and validate the three FAISS artifacts."""
    for path in (INDEX_PATH, IDS_PATH, META_PATH):
        if not path.exists():
            print(f"Error: artifact not found: {path}", file=sys.stderr)
            print("Run embed_chunks.py first.", file=sys.stderr)
            sys.exit(1)

    meta      = json.loads(META_PATH.read_text(encoding="utf-8"))
    ids_array = np.load(str(IDS_PATH))
    index     = faiss.read_index(str(INDEX_PATH))

    errors = []
    locked = {
        "artifact":            "chunks",
        "artifact_version":    1,
        "embedding_model":     EMBEDDING_MODEL,
        "faiss_index_type":    "IndexFlatIP",
        "metric":              "cosine_via_normalized_inner_product",
        "normalized":          True,
        "source_table":        "chunks",
        "source_text_column":  "text",
        "source_id_column":    "id",
        "build_order":         "id ASC",
        "vector_dtype":        "float32",
        "id_dtype":            "int64",
    }
    for field, expected in locked.items():
        if meta.get(field) != expected:
            errors.append(
                f"metadata '{field}': expected {expected!r}, got {meta.get(field)!r}"
            )
    if ids_array.ndim != 1:
        errors.append(f"ids ndim={ids_array.ndim}, expected 1")
    if ids_array.dtype != np.int64:
        errors.append(f"ids dtype={ids_array.dtype}, expected int64")
    chunk_count = meta.get("chunk_count")
    if len(ids_array) != chunk_count:
        errors.append(f"ids length {len(ids_array)} != chunk_count {chunk_count}")
    if index.ntotal != chunk_count:
        errors.append(f"FAISS ntotal {index.ntotal} != chunk_count {chunk_count}")
    if index.d != meta.get("embedding_dimension"):
        errors.append(
            f"FAISS dimension {index.d} != embedding_dimension {meta.get('embedding_dimension')}"
        )
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    return meta, ids_array, index


def embed_query(client: OpenAI, query: str, expected_dim: int) -> np.ndarray:
    """Embed and L2-normalize a single query string."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    vec = np.array(response.data[0].embedding, dtype=np.float32)
    if vec.shape[0] != expected_dim:
        print(
            f"Error: query vector dimension {vec.shape[0]} != index dimension {expected_dim}.",
            file=sys.stderr,
        )
        sys.exit(1)
    norm = np.linalg.norm(vec)
    if norm == 0:
        print("Error: query vector has zero norm.", file=sys.stderr)
        sys.exit(1)
    return (vec / norm).reshape(1, -1)


def run_vector(
    conn: sqlite3.Connection,
    client: OpenAI,
    query: str,
    meta: dict,
    ids_array: np.ndarray,
    index: faiss.Index,
) -> list[dict]:
    """
    Run vector retrieval. Returns rows with vector_rank (1-based) and vector_score.
    """
    D = meta["embedding_dimension"]
    query_vec = embed_query(client, query, D)

    scores_arr, positions_arr = index.search(query_vec, VECTOR_CANDIDATES)
    scores    = scores_arr[0].tolist()
    positions = positions_arr[0].tolist()

    hit_pairs = [
        (int(ids_array[pos]), score)
        for pos, score in zip(positions, scores)
        if pos != -1
    ]
    if not hit_pairs:
        return []

    hit_ids = [cid for cid, _ in hit_pairs]
    placeholders = ", ".join("?" * len(hit_ids))
    sql = VECTOR_META_SQL.format(placeholders=placeholders)
    db_rows = conn.execute(sql, hit_ids).fetchall()
    row_by_id = {row["chunk_id"]: row for row in db_rows}

    missing = [cid for cid in hit_ids if cid not in row_by_id]
    if missing:
        print(
            f"Error: {len(missing)} chunk IDs from FAISS not found in SQLite: {missing[:5]}",
            file=sys.stderr,
        )
        sys.exit(1)

    results = []
    for rank, (chunk_id, score) in enumerate(hit_pairs, start=1):
        row = row_by_id[chunk_id]
        results.append({
            "chunk_id":          row["chunk_id"],
            "chunk_index":       row["chunk_index"],
            "opinion_id":        row["opinion_id"],
            "source_opinion_id": row["source_opinion_id"],
            "case_id":           row["case_id"],
            "source_docket_id":  row["source_docket_id"],
            "case_name":         row["case_name"],
            "docket_number":     row["docket_number"],
            "char_start":        row["char_start"],
            "char_end":          row["char_end"],
            "text":              row["text"],
            "vector_score":      score,
            "vector_rank":       rank,
        })
    return results


# ── RRF merge ──────────────────────────────────────────────────────────────────

def merge_rrf(fts_rows: list[dict], vec_rows: list[dict]) -> list[dict]:
    """
    Merge FTS and vector results using weighted RRF.
    Fails clearly if the same chunk_id has conflicting metadata.
    """
    merged: dict[int, dict] = {}

    for row in fts_rows:
        cid = row["chunk_id"]
        merged[cid] = {
            field: row[field] for field in (
                "chunk_id", "chunk_index", "opinion_id", "source_opinion_id",
                "case_id", "source_docket_id", "case_name", "docket_number",
                "char_start", "char_end", "text",
            )
        }
        merged[cid]["fts_score"]    = row["fts_score"]
        merged[cid]["fts_rank"]     = row["fts_rank"]
        merged[cid]["vector_score"] = None
        merged[cid]["vector_rank"]  = None
        merged[cid]["matched_by"]   = "fts"

    for row in vec_rows:
        cid = row["chunk_id"]
        if cid in merged:
            # Validate metadata agreement
            conflicts = []
            for field in _CHUNK_META_FIELDS:
                if merged[cid][field] != row[field]:
                    conflicts.append(
                        f"  {field}: fts={merged[cid][field]!r} vs vector={row[field]!r}"
                    )
            if conflicts:
                raise RuntimeError(
                    f"Metadata mismatch for chunk_id={cid}:\n" + "\n".join(conflicts)
                )
            merged[cid]["vector_score"] = row["vector_score"]
            merged[cid]["vector_rank"]  = row["vector_rank"]
            merged[cid]["matched_by"]   = "both"
        else:
            merged[cid] = {
                field: row[field] for field in (
                    "chunk_id", "chunk_index", "opinion_id", "source_opinion_id",
                    "case_id", "source_docket_id", "case_name", "docket_number",
                    "char_start", "char_end", "text",
                )
            }
            merged[cid]["fts_score"]    = None
            merged[cid]["fts_rank"]     = None
            merged[cid]["vector_score"] = row["vector_score"]
            merged[cid]["vector_rank"]  = row["vector_rank"]
            merged[cid]["matched_by"]   = "vector"

    # Compute RRF scores and add preview
    results = []
    for row in merged.values():
        fts_contrib = (
            FTS_WEIGHT / (RRF_K + row["fts_rank"])
            if row["fts_rank"] is not None else 0.0
        )
        vec_contrib = (
            VECTOR_WEIGHT / (RRF_K + row["vector_rank"])
            if row["vector_rank"] is not None else 0.0
        )
        row["combined_score"] = fts_contrib + vec_contrib
        row["preview"]        = make_preview(row["text"])
        results.append(row)

    # Sort: combined_score desc, both > single, best rank asc, chunk_id asc
    def sort_key(r: dict) -> tuple:
        matched_by_order = 0 if r["matched_by"] == "both" else 1
        ranks = [x for x in (r["fts_rank"], r["vector_rank"]) if x is not None]
        best_rank = min(ranks) if ranks else 999999
        return (-r["combined_score"], matched_by_order, best_rank, r["chunk_id"])

    results.sort(key=sort_key)
    return results


# ── Output ─────────────────────────────────────────────────────────────────────

def fmt_optional(value, fmt: str = ".4f") -> str:
    return f"{value:{fmt}}" if value is not None else "—"


def print_results(query: str, hits: list[dict]) -> None:
    print(f'Query: "{query}"')
    if not hits:
        print(f'No results found for query: "{query}"')
        return

    print(f"Hits:  {len(hits)}")
    for i, hit in enumerate(hits, start=1):
        docket = hit["docket_number"] or "—"
        print(f"\n{i}. {hit['case_name']} ({docket})  [{hit['matched_by']}]")
        print(
            f"   combined={hit['combined_score']:.6f}"
            f"  fts_rank={fmt_optional(hit['fts_rank'], 'd')}"
            f"  vec_rank={fmt_optional(hit['vector_rank'], 'd')}"
            f"  fts_score={fmt_optional(hit['fts_score'])}"
            f"  vec_score={fmt_optional(hit['vector_score'])}"
        )
        print(
            f"   chunk_id={hit['chunk_id']}"
            f"  opinion_id={hit['opinion_id']}"
            f"  case_id={hit['case_id']}"
            f"  source_docket_id={hit['source_docket_id']}"
        )
        print(
            f"   opinion={hit['source_opinion_id']}"
            f"  chunk={hit['chunk_index']}"
            f"  chars={hit['char_start']}:{hit['char_end']}"
        )
        print(f"   {hit['preview']}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(
        description="Hybrid FTS + vector search over the legal casebase."
    )
    parser.add_argument("query", help="Query string")
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Maximum number of results (default: 10)",
    )
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be greater than 0")
    if not args.query.strip():
        parser.error("query must not be empty or whitespace-only")
    return args


def main() -> None:
    args = parse_args()

    # Run FTS first so invalid query syntax surfaces before vector prerequisites.
    with get_connection() as conn:
        fts_rows = run_fts(conn, args.query)

    # Only after FTS succeeds: check API key, load artifacts, run vector search.
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("Error: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    meta, ids_array, index = load_vector_artifacts()

    with get_connection() as conn:
        vec_rows = run_vector(conn, client, args.query, meta, ids_array, index)

    merged = merge_rrf(fts_rows, vec_rows)
    hits   = merged[: args.limit]
    print_results(args.query, hits)


if __name__ == "__main__":
    main()
