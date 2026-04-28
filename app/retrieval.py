"""
app/retrieval.py

Reusable retrieval module mirroring the behavior of:
  scripts/search_fts.py
  scripts/search_vector.py
  scripts/search_hybrid.py

Key difference from the scripts: raises exceptions instead of
printing errors and calling sys.exit().

Public API:
    search_casebase(query, limit, mode) -> list[dict]
    search_fts(query, limit)            -> list[dict]
    search_vector(query, limit)         -> list[dict]
    search_hybrid(query, limit)         -> list[dict]

Raises:
    ValueError  — empty/whitespace query, limit <= 0, invalid mode
    RuntimeError — all infrastructure / data failures
"""

import json
import os
import re
import sqlite3
from pathlib import Path

import faiss
import numpy as np
from openai import OpenAI

from app.db import get_connection

# ── Constants (mirrors search_hybrid.py) ──────────────────────────────────────

FTS_CANDIDATES    = 20
VECTOR_CANDIDATES = 20
RRF_K             = 60
FTS_WEIGHT        = 1.0
VECTOR_WEIGHT     = 1.0
EMBEDDING_MODEL   = "text-embedding-3-small"
PREVIEW_CHARS     = 220

ROOT       = Path(__file__).resolve().parents[1]
FAISS_DIR  = ROOT / "storage" / "faiss"
INDEX_PATH = FAISS_DIR / "chunks.index"
IDS_PATH   = FAISS_DIR / "chunks_ids.npy"
META_PATH  = FAISS_DIR / "chunks_meta.json"

# Mirrors search_hybrid._CHUNK_META_FIELDS
_CHUNK_META_FIELDS = (
    "chunk_index", "opinion_id", "source_opinion_id",
    "case_id", "source_docket_id", "case_name",
    "docket_number", "char_start", "char_end", "text",
)

# ── SQL (mirrors the scripts exactly) ─────────────────────────────────────────

# From search_fts.py (with fts_score alias instead of score, and text added)
_FTS_SQL = """
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
    bm25(chunks_fts)                              AS fts_score,
    snippet(chunks_fts, 0, '[', ']', ' \u2026 ', 12) AS snippet
FROM chunks_fts
JOIN chunks   c  ON c.id = chunks_fts.rowid
JOIN opinions o  ON o.id = c.opinion_id
JOIN cases    cs ON cs.id = c.case_id
WHERE chunks_fts MATCH ?
ORDER BY fts_score ASC, c.id ASC
LIMIT ?
"""

# From search_vector.py / search_hybrid.py
_VECTOR_META_SQL = """
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

# ── Shared utilities ───────────────────────────────────────────────────────────

_WS_RE = re.compile(r"\s+")


def _make_preview(text: str, max_chars: int = PREVIEW_CHARS) -> str:
    """Mirrors search_hybrid.make_preview / search_vector.make_preview."""
    normalized = _WS_RE.sub(" ", text).strip()
    return normalized[:max_chars] + "…" if len(normalized) > max_chars else normalized


def _validate_inputs(query: str, limit: int) -> None:
    if not query or not query.strip():
        raise ValueError("Query must not be empty or whitespace-only.")
    if limit <= 0:
        raise ValueError(f"Limit must be > 0, got {limit}.")


# ── Vector artifact loading (mirrors search_hybrid.load_vector_artifacts) ──────

def _load_vector_artifacts() -> tuple[dict, np.ndarray, faiss.Index]:
    for path in (INDEX_PATH, IDS_PATH, META_PATH):
        if not path.exists():
            raise RuntimeError(
                f"Artifact not found: {path}. Run embed_chunks.py first."
            )

    meta      = json.loads(META_PATH.read_text(encoding="utf-8"))
    ids_array = np.load(str(IDS_PATH))
    index     = faiss.read_index(str(INDEX_PATH))

    errors = []
    if ids_array.ndim != 1:
        errors.append(f"chunks_ids.npy must be 1-D, got ndim={ids_array.ndim}")
    if ids_array.dtype != np.int64:
        errors.append(f"chunks_ids.npy must be dtype int64, got {ids_array.dtype}")

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
        actual = meta.get(field)
        if actual != expected:
            errors.append(f"metadata '{field}': expected {expected!r}, got {actual!r}")

    chunk_count = meta.get("chunk_count")
    if len(ids_array) != chunk_count:
        errors.append(f"ids array length {len(ids_array)} != chunk_count {chunk_count}")
    if index.ntotal != chunk_count:
        errors.append(f"FAISS ntotal {index.ntotal} != chunk_count {chunk_count}")
    if index.d != meta.get("embedding_dimension"):
        errors.append(
            f"FAISS dimension {index.d} != embedding_dimension {meta.get('embedding_dimension')}"
        )
    if errors:
        raise RuntimeError("Invalid vector artifacts:\n  " + "\n  ".join(errors))

    return meta, ids_array, index


def _make_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=api_key)


def _embed_query(client: OpenAI, query: str, expected_dim: int) -> np.ndarray:
    """Mirrors search_hybrid.embed_query / search_vector.embed_query."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    vec = np.array(response.data[0].embedding, dtype=np.float32)
    if vec.shape[0] != expected_dim:
        raise RuntimeError(
            f"Query vector dimension {vec.shape[0]} != index dimension {expected_dim}."
        )
    norm = np.linalg.norm(vec)
    if norm == 0:
        raise RuntimeError("Query vector has zero norm.")
    return (vec / norm).reshape(1, -1)


# ── FTS retrieval (mirrors search_hybrid.run_fts) ─────────────────────────────

def _run_fts(conn, query: str, limit: int) -> list[dict]:
    try:
        rows = conn.execute(_FTS_SQL, (query, limit)).fetchall()
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        if any(kw in msg for kw in (
            "fts5", "match", "syntax",
            "unterminated string", "parse error", "malformed",
        )):
            raise RuntimeError(f"Invalid FTS query syntax: {e}") from e
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
            "snippet":           row["snippet"],
            "fts_score":         row["fts_score"],
            "fts_rank":          rank,
        })
    return results


# ── Vector retrieval (mirrors search_hybrid.run_vector) ───────────────────────

def _run_vector(
    conn,
    client: OpenAI,
    query: str,
    meta: dict,
    ids_array: np.ndarray,
    index: faiss.Index,
    limit: int,
) -> list[dict]:
    D = meta["embedding_dimension"]
    query_vec = _embed_query(client, query, D)

    scores_arr, positions_arr = index.search(query_vec, limit)
    hit_pairs = [
        (int(ids_array[pos]), float(score))
        for pos, score in zip(positions_arr[0], scores_arr[0])
        if pos != -1
    ]
    if not hit_pairs:
        return []

    hit_ids = [cid for cid, _ in hit_pairs]
    sql = _VECTOR_META_SQL.format(placeholders=", ".join("?" * len(hit_ids)))
    db_rows = conn.execute(sql, hit_ids).fetchall()
    row_by_id = {row["chunk_id"]: row for row in db_rows}

    missing = [cid for cid in hit_ids if cid not in row_by_id]
    if missing:
        raise RuntimeError(
            f"{len(missing)} chunk IDs from FAISS not found in SQLite: {missing[:5]}"
        )

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


# ── RRF merge (mirrors search_hybrid.merge_rrf exactly) ───────────────────────

def _merge_rrf(fts_rows: list[dict], vec_rows: list[dict]) -> list[dict]:
    merged: dict[int, dict] = {}

    for row in fts_rows:
        cid = row["chunk_id"]
        merged[cid] = {f: row[f] for f in (
            "chunk_id", "chunk_index", "opinion_id", "source_opinion_id",
            "case_id", "source_docket_id", "case_name", "docket_number",
            "char_start", "char_end", "text",
        )}
        merged[cid]["fts_score"]    = row["fts_score"]
        merged[cid]["fts_rank"]     = row["fts_rank"]
        merged[cid]["vector_score"] = None
        merged[cid]["vector_rank"]  = None
        merged[cid]["matched_by"]   = "fts"

    for row in vec_rows:
        cid = row["chunk_id"]
        if cid in merged:
            conflicts = [
                f"  {f}: fts={merged[cid][f]!r} vs vector={row[f]!r}"
                for f in _CHUNK_META_FIELDS
                if merged[cid][f] != row[f]
            ]
            if conflicts:
                raise RuntimeError(
                    f"Metadata mismatch for chunk_id={cid}:\n" + "\n".join(conflicts)
                )
            merged[cid]["vector_score"] = row["vector_score"]
            merged[cid]["vector_rank"]  = row["vector_rank"]
            merged[cid]["matched_by"]   = "both"
        else:
            merged[cid] = {f: row[f] for f in (
                "chunk_id", "chunk_index", "opinion_id", "source_opinion_id",
                "case_id", "source_docket_id", "case_name", "docket_number",
                "char_start", "char_end", "text",
            )}
            merged[cid]["fts_score"]    = None
            merged[cid]["fts_rank"]     = None
            merged[cid]["vector_score"] = row["vector_score"]
            merged[cid]["vector_rank"]  = row["vector_rank"]
            merged[cid]["matched_by"]   = "vector"

    results = []
    for row in merged.values():
        fts_c = FTS_WEIGHT / (RRF_K + row["fts_rank"]) if row["fts_rank"] is not None else 0.0
        vec_c = VECTOR_WEIGHT / (RRF_K + row["vector_rank"]) if row["vector_rank"] is not None else 0.0
        row["combined_score"] = fts_c + vec_c
        row["preview"]        = _make_preview(row["text"])
        results.append(row)

    def _sort_key(r: dict) -> tuple:
        order = 0 if r["matched_by"] == "both" else 1
        ranks = [x for x in (r["fts_rank"], r["vector_rank"]) if x is not None]
        return (-r["combined_score"], order, min(ranks) if ranks else 999999, r["chunk_id"])

    results.sort(key=_sort_key)
    return results


# ── Public API ─────────────────────────────────────────────────────────────────

def search_fts(query: str, limit: int = 10) -> list[dict]:
    """
    Keyword search. Mirrors scripts/search_fts.py behavior.
    Returns dicts with fts_score, snippet, preview.
    matched_by='fts', vector fields None, combined_score None.
    """
    _validate_inputs(query, limit)
    with get_connection() as conn:
        rows = _run_fts(conn, query, limit)

    return [
        {
            **{k: r[k] for k in (
                "chunk_id", "chunk_index", "opinion_id", "source_opinion_id",
                "case_id", "source_docket_id", "case_name", "docket_number",
                "char_start", "char_end", "text",
            )},
            "preview":        _make_preview(r["text"]),
            "snippet":        r["snippet"],
            "fts_score":      r["fts_score"],
            "fts_rank":       r["fts_rank"],
            "vector_score":   None,
            "vector_rank":    None,
            "combined_score": None,
            "matched_by":     "fts",
        }
        for r in rows
    ]


def search_vector(query: str, limit: int = 10) -> list[dict]:
    """
    Vector similarity search. Mirrors scripts/search_vector.py behavior.
    Returns dicts with vector_score, preview.
    matched_by='vector', FTS fields None, combined_score None.
    """
    _validate_inputs(query, limit)
    client = _make_openai_client()
    meta, ids_array, index = _load_vector_artifacts()
    with get_connection() as conn:
        rows = _run_vector(conn, client, query, meta, ids_array, index, limit)

    return [
        {
            **{k: r[k] for k in (
                "chunk_id", "chunk_index", "opinion_id", "source_opinion_id",
                "case_id", "source_docket_id", "case_name", "docket_number",
                "char_start", "char_end", "text",
            )},
            "preview":        _make_preview(r["text"]),
            "snippet":        None,
            "fts_score":      None,
            "fts_rank":       None,
            "vector_score":   r["vector_score"],
            "vector_rank":    r["vector_rank"],
            "combined_score": None,
            "matched_by":     "vector",
        }
        for r in rows
    ]


def search_hybrid(query: str, limit: int = 10) -> list[dict]:
    """
    Hybrid RRF search. Mirrors scripts/search_hybrid.py behavior exactly.
    FTS runs first so syntax errors surface before vector prerequisites.
    """
    _validate_inputs(query, limit)

    # FTS first — mirrors main() ordering in search_hybrid.py
    with get_connection() as conn:
        fts_rows = _run_fts(conn, query, FTS_CANDIDATES)

    # After FTS succeeds: client before artifacts, mirroring the script
    client = _make_openai_client()
    meta, ids_array, index = _load_vector_artifacts()

    with get_connection() as conn:
        vec_rows = _run_vector(
            conn, client, query, meta, ids_array, index, VECTOR_CANDIDATES
        )

    merged = _merge_rrf(fts_rows, vec_rows)
    return merged[:limit]


def search_casebase(query: str, limit: int = 10, mode: str = "hybrid") -> list[dict]:
    """Unified entry point dispatching to fts / vector / hybrid."""
    if mode == "fts":
        return search_fts(query, limit)
    elif mode == "vector":
        return search_vector(query, limit)
    elif mode == "hybrid":
        return search_hybrid(query, limit)
    else:
        raise ValueError(
            f"Invalid mode {mode!r}. Must be 'fts', 'vector', or 'hybrid'."
        )
