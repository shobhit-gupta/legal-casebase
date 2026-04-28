# Retrieval Contract

## Retrieval unit
- Canonical retrieval unit: `chunk`
- Source table: `chunks`
- Returned metadata is joined from:
  - `chunks`
  - `opinions`
  - `cases`

## Retrieval modes
1. `fts`
   - exact / keyword retrieval over `chunks_fts`
   - ranks by `bm25(chunks_fts)` ascending
   - good for exact legal phrases, citations, names, statutory language

2. `vector`
   - semantic retrieval over FAISS index built from `chunks.text`
   - embedding model: `text-embedding-3-small`
   - similarity semantics: cosine via normalized vectors + `IndexFlatIP`
   - good for paraphrases and broader conceptual recall

3. `hybrid`
   - runs both FTS and vector retrieval
   - merges by `chunk_id`
   - ranking uses Reciprocal Rank Fusion (RRF)

## Hybrid configuration
- `FTS_CANDIDATES = 20`
- `VECTOR_CANDIDATES = 20`
- `RRF_K = 60`
- `FTS_WEIGHT = 1.0`
- `VECTOR_WEIGHT = 1.0`

## Hybrid score
For a chunk:
- FTS contribution = `FTS_WEIGHT / (RRF_K + fts_rank)` if present
- Vector contribution = `VECTOR_WEIGHT / (RRF_K + vector_rank)` if present
- Combined score = sum of both

## Merge invariant
If the same `chunk_id` appears in both sources, these fields must agree:
- `chunk_index`
- `opinion_id`
- `source_opinion_id`
- `case_id`
- `source_docket_id`
- `case_name`
- `docket_number`
- `char_start`
- `char_end`
- `text`

## Current output level
- Current retrieval output is chunk-level
- Grouping by opinion or case is deferred

## Product default
- Intended default retrieval mode for product-facing usage: `hybrid`
- `fts` and `vector` remain useful as internal/debug modes