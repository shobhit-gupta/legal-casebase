"""
scripts/embed_chunks.py

Reads chunk text from SQLite, generates OpenAI embeddings,
L2-normalizes vectors, builds a FAISS IndexFlatIP, and writes
three artifacts:

    storage/faiss/chunks.index
    storage/faiss/chunks_ids.npy
    storage/faiss/chunks_meta.json

Full reset / rebuild only. No incremental indexing.
No vectors stored in SQLite.

Usage:
    python scripts/embed_chunks.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import faiss
import numpy as np
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import get_connection

FAISS_DIR     = ROOT / "storage" / "faiss"
INDEX_PATH    = FAISS_DIR / "chunks.index"
IDS_PATH      = FAISS_DIR / "chunks_ids.npy"
META_PATH     = FAISS_DIR / "chunks_meta.json"

EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE      = 64


# ── Embedding ──────────────────────────────────────────────────────────────────

def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Call the OpenAI embeddings API for a batch of texts."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    # Response items are ordered to match input order
    return [item.embedding for item in response.data]


# ── Normalization ──────────────────────────────────────────────────────────────

def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    """L2-normalize each row. Raises if any row has zero norm."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        zero_rows = np.where(norms.flatten() == 0)[0].tolist()
        raise RuntimeError(
            f"Zero-norm vectors at rows: {zero_rows}. Cannot normalize."
        )
    return (matrix / norms).astype(np.float32)


# ── Post-publish validation ────────────────────────────────────────────────────

def _validate_published_artifacts(
    built_meta: dict,
    built_ids: np.ndarray,
    N: int,
    D: int,
) -> None:
    """
    Reload the three artifact files from disk and verify they match the
    just-built artifacts. Always called after the publish sequence — even
    if a publish step failed — to detect mixed/inconsistent artifact sets.

    Raises RuntimeError listing all failures found.
    """
    errors: list[str] = []

    # Load finals — missing file is itself a failure
    try:
        published_meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"Cannot read {META_PATH}: {e}")
        published_meta = {}

    try:
        published_ids = np.load(str(IDS_PATH))
    except Exception as e:
        errors.append(f"Cannot read {IDS_PATH}: {e}")
        published_ids = None

    try:
        published_index = faiss.read_index(str(INDEX_PATH))
    except Exception as e:
        errors.append(f"Cannot read {INDEX_PATH}: {e}")
        published_index = None

    # IDs array shape, dtype, and equality
    if published_ids is not None:
        if published_ids.ndim != 1:
            errors.append(
                f"published ids ndim={published_ids.ndim}, expected 1"
            )
        if published_ids.dtype != np.int64:
            errors.append(
                f"published ids dtype={published_ids.dtype}, expected int64"
            )
        if not np.array_equal(published_ids, built_ids):
            errors.append("published ids array does not match built ids array")

    # Metadata locked fields must exactly match what was built
    locked_fields = [
        "artifact", "artifact_version", "embedding_model",
        "embedding_dimension", "vector_dtype", "id_dtype",
        "faiss_index_type", "metric", "normalized",
        "source_table", "source_text_column", "source_id_column",
        "build_order", "chunk_count",
    ]
    for field in locked_fields:
        expected = built_meta.get(field)
        actual   = published_meta.get(field)
        if actual != expected:
            errors.append(
                f"metadata '{field}': published={actual!r}, built={expected!r}"
            )

    # FAISS index shape
    if published_index is not None:
        if published_index.ntotal != N:
            errors.append(
                f"published FAISS ntotal={published_index.ntotal}, expected {N}"
            )
        if published_index.d != D:
            errors.append(
                f"published FAISS dimension={published_index.d}, expected {D}"
            )

    if errors:
        raise RuntimeError(
            "Artifact set is missing or inconsistent:\n  " + "\n  ".join(errors)
        )


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Validate prerequisites
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("Error: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    FAISS_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key)

    # 2. Read source rows
    print("Reading chunks from SQLite...")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, text FROM chunks WHERE text IS NOT NULL ORDER BY id ASC"
        ).fetchall()

    chunk_ids: list[int] = []
    chunk_texts: list[str] = []
    skipped = 0

    for row in rows:
        text = row["text"] or ""
        if not text.strip():
            print(f"  [skip] chunk id={row['id']}: whitespace-only text")
            skipped += 1
            continue
        chunk_ids.append(row["id"])
        chunk_texts.append(text)

    if not chunk_texts:
        print("Error: no usable chunk rows found. Run chunk.py first.", file=sys.stderr)
        sys.exit(1)

    N = len(chunk_texts)
    print(f"  {N} usable chunks ({skipped} skipped)\n")

    # 3. Generate embeddings in batches
    print(f"Embedding {N} chunks in batches of {BATCH_SIZE}...")
    all_vectors: list[list[float]] = []

    for start in range(0, N, BATCH_SIZE):
        batch = chunk_texts[start : start + BATCH_SIZE]
        batch_num = start // BATCH_SIZE + 1
        total_batches = (N + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  batch {batch_num}/{total_batches} ({len(batch)} texts)")
        vectors = embed_texts(client, batch)
        all_vectors.extend(vectors)

    # 4. Validate embedding results
    if len(all_vectors) != N:
        raise RuntimeError(
            f"Expected {N} vectors but got {len(all_vectors)}."
        )
    D = len(all_vectors[0])
    for i, v in enumerate(all_vectors):
        if len(v) != D:
            raise RuntimeError(
                f"Inconsistent embedding dimension at index {i}: "
                f"expected {D}, got {len(v)}."
            )

    matrix = np.array(all_vectors, dtype=np.float32)
    print(f"\n  Embedding dimension: {D}")

    # 5. Normalize vectors
    print("L2-normalizing vectors...")
    matrix = l2_normalize(matrix)

    # 6. Build FAISS index
    print("Building FAISS IndexFlatIP...")
    index = faiss.IndexFlatIP(D)
    index.add(matrix)
    if index.ntotal != N:
        raise RuntimeError(f"FAISS ntotal {index.ntotal} != N {N} after add.")

    # 7. Build ids array
    ids_array = np.array(chunk_ids, dtype=np.int64)
    if len(ids_array) != N:
        raise RuntimeError(f"ids_array length {len(ids_array)} != N {N}.")

    # 8. Build metadata
    meta = {
        "artifact":            "chunks",
        "artifact_version":    1,
        "embedding_model":     EMBEDDING_MODEL,
        "embedding_dimension": D,
        "vector_dtype":        "float32",
        "id_dtype":            "int64",
        "faiss_index_type":    "IndexFlatIP",
        "metric":              "cosine_via_normalized_inner_product",
        "normalized":          True,
        "source_table":        "chunks",
        "source_text_column":  "text",
        "source_id_column":    "id",
        "build_order":         "id ASC",
        "chunk_count":         N,
        "rebuilt_at":          datetime.now(timezone.utc).isoformat(),
    }

    # 9. Write artifacts safely via temp files, then publish
    print("Writing artifacts...")
    index_tmp = INDEX_PATH.with_suffix(".index.tmp")
    ids_tmp   = FAISS_DIR / "chunks_ids.tmp.npy"
    meta_tmp  = META_PATH.with_suffix(".json.tmp")

    publish_error: Exception | None = None
    try:
        faiss.write_index(index, str(index_tmp))
        np.save(str(ids_tmp), ids_array)
        meta_tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # replace() is overwrite-safe on POSIX/Windows.
        # If one replace succeeds and a later one fails, the final artifact set
        # may be mixed. The validation below always runs against the actual
        # finals on disk, catching that case.
        index_tmp.replace(INDEX_PATH)
        ids_tmp.replace(IDS_PATH)
        meta_tmp.replace(META_PATH)
    except Exception as e:
        publish_error = e
        for p in (index_tmp, ids_tmp, meta_tmp):
            p.unlink(missing_ok=True)
    finally:
        # Always validate the final artifact set on disk — even if a publish
        # step failed — so a mixed/inconsistent set is caught and reported.
        print("Verifying published artifacts...")
        _validate_published_artifacts(meta, ids_array, N, D)

    # If publish failed but validation passed (shouldn't happen), still raise.
    if publish_error is not None:
        raise RuntimeError(
            f"Artifact publish failed: {publish_error}"
        ) from publish_error

    print("  Artifacts verified.")

    # 10. Summary
    print(
        f"\nDone."
        f"\n  Embedded:  {N} chunks"
        f"\n  Skipped:   {skipped} chunks"
        f"\n  Dimension: {D}"
        f"\n  Model:     {EMBEDDING_MODEL}"
        f"\n  Index:     {INDEX_PATH}"
        f"\n  IDs:       {IDS_PATH}"
        f"\n  Meta:      {META_PATH}"
    )


if __name__ == "__main__":
    main()
