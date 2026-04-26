"""
scripts/search_vector.py

Embeds a query using OpenAI text-embedding-3-small, searches the FAISS
index of chunk vectors, and prints chunk-level results with metadata.

Higher score = better match (cosine similarity via normalized inner product).

Usage:
    python scripts/search_vector.py "query string" [--limit N]
"""

import json
import os
import re
import sys
from pathlib import Path

import faiss
import numpy as np
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import get_connection

FAISS_DIR  = ROOT / "storage" / "faiss"
INDEX_PATH = FAISS_DIR / "chunks.index"
IDS_PATH   = FAISS_DIR / "chunks_ids.npy"
META_PATH  = FAISS_DIR / "chunks_meta.json"

EMBEDDING_MODEL = "text-embedding-3-small"
PREVIEW_CHARS   = 220

METADATA_QUERY = """
SELECT
    c.id         AS chunk_id,
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


# ── Artifacts ──────────────────────────────────────────────────────────────────

def load_artifacts() -> tuple[dict, np.ndarray, faiss.Index]:
    """Load and validate the three FAISS artifacts."""
    for path in (INDEX_PATH, IDS_PATH, META_PATH):
        if not path.exists():
            print(f"Error: artifact not found: {path}", file=sys.stderr)
            print("Run embed_chunks.py first.", file=sys.stderr)
            sys.exit(1)

    meta      = json.loads(META_PATH.read_text(encoding="utf-8"))
    ids_array = np.load(str(IDS_PATH))
    index     = faiss.read_index(str(INDEX_PATH))

    # Validate ids array shape and dtype
    errors = []
    if ids_array.ndim != 1:
        errors.append(f"chunks_ids.npy must be 1-D, got ndim={ids_array.ndim}")
    if ids_array.dtype != np.int64:
        errors.append(f"chunks_ids.npy must be dtype int64, got {ids_array.dtype}")

    # Validate full locked metadata contract
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
            errors.append(
                f"metadata '{field}': expected {expected!r}, got {actual!r}"
            )

    # Validate numeric consistency between meta, ids, and FAISS index
    chunk_count = meta.get("chunk_count")
    if len(ids_array) != chunk_count:
        errors.append(
            f"ids array length {len(ids_array)} != chunk_count {chunk_count}"
        )
    if index.ntotal != chunk_count:
        errors.append(
            f"FAISS ntotal {index.ntotal} != chunk_count {chunk_count}"
        )
    if index.d != meta.get("embedding_dimension"):
        errors.append(
            f"FAISS dimension {index.d} != metadata embedding_dimension {meta.get('embedding_dimension')}"
        )
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    return meta, ids_array, index


# ── Embedding ──────────────────────────────────────────────────────────────────

def embed_query(client: OpenAI, query: str, expected_dim: int) -> np.ndarray:
    """Embed a single query string, normalize, and return as float32 row vector."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    vec = np.array(response.data[0].embedding, dtype=np.float32)

    if vec.shape[0] != expected_dim:
        print(
            f"Error: query vector dimension {vec.shape[0]} != "
            f"index dimension {expected_dim}.",
            file=sys.stderr,
        )
        sys.exit(1)

    norm = np.linalg.norm(vec)
    if norm == 0:
        print("Error: query vector has zero norm.", file=sys.stderr)
        sys.exit(1)

    return (vec / norm).reshape(1, -1)


# ── Output ─────────────────────────────────────────────────────────────────────

_WS_RE = re.compile(r"\s+")


def make_preview(text: str, max_chars: int = PREVIEW_CHARS) -> str:
    """Return the first max_chars characters with whitespace normalized."""
    normalized = _WS_RE.sub(" ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars] + "…"


def print_results(query: str, hits: list[dict]) -> None:
    print(f'Query: "{query}"')
    if not hits:
        print(f'No results found for query: "{query}"')
        return

    print(f"Hits:  {len(hits)}")
    for i, hit in enumerate(hits, start=1):
        docket = hit["docket_number"] or "—"
        print(f"\n{i}. {hit['case_name']} ({docket})")
        print(
            f"   chunk_id={hit['chunk_id']}"
            f"  opinion_id={hit['opinion_id']}"
            f"  case_id={hit['case_id']}"
            f"  source_docket_id={hit['source_docket_id']}"
        )
        print(
            f"   opinion={hit['source_opinion_id']}"
            f"  chunk={hit['chunk_index']}"
            f"  score={hit['score']:.4f}"
            f"  chars={hit['char_start']}:{hit['char_end']}"
        )
        print(f"   {hit['preview']}")


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(
        description="Vector search over the legal casebase FAISS index."
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

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("Error: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    # 2. Load and validate artifacts
    meta, ids_array, index = load_artifacts()
    D = meta["embedding_dimension"]

    # 3. Embed query
    query_vec = embed_query(client, args.query, D)

    # 4. FAISS search
    scores_arr, positions_arr = index.search(query_vec, args.limit)
    scores    = scores_arr[0].tolist()
    positions = positions_arr[0].tolist()

    # Map positions to chunk IDs, discard invalid (-1) entries
    hit_pairs: list[tuple[int, float]] = []  # (chunk_id, score)
    for pos, score in zip(positions, scores):
        if pos == -1:
            continue
        hit_pairs.append((int(ids_array[pos]), score))

    if not hit_pairs:
        print_results(args.query, [])
        return

    # 5. Load metadata from SQLite
    hit_ids = [cid for cid, _ in hit_pairs]
    placeholders = ", ".join("?" * len(hit_ids))
    sql = METADATA_QUERY.format(placeholders=placeholders)

    with get_connection() as conn:
        db_rows = conn.execute(sql, hit_ids).fetchall()

    # Build lookup by chunk_id
    row_by_id = {row["chunk_id"]: row for row in db_rows}

    missing = [cid for cid in hit_ids if cid not in row_by_id]
    if missing:
        print(
            f"Error: {len(missing)} chunk IDs returned by FAISS not found in SQLite: "
            f"{missing[:5]}{'...' if len(missing) > 5 else ''}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 6. Build output rows in FAISS rank order
    hits = []
    for chunk_id, score in hit_pairs:
        row = row_by_id[chunk_id]
        hits.append({
            "chunk_id":         row["chunk_id"],
            "chunk_index":      row["chunk_index"],
            "opinion_id":       row["opinion_id"],
            "source_opinion_id": row["source_opinion_id"],
            "case_id":          row["case_id"],
            "source_docket_id": row["source_docket_id"],
            "case_name":        row["case_name"],
            "docket_number":    row["docket_number"],
            "char_start":       row["char_start"],
            "char_end":         row["char_end"],
            "score":            score,
            "preview":          make_preview(row["text"]),
        })

    # 7. Print results
    print_results(args.query, hits)


if __name__ == "__main__":
    main()
