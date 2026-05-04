## Data preparation pipeline

The demo corpus is prepared through the following script sequence:

```bash
docker compose run --rm app python scripts/fetch.py
docker compose run --rm app python scripts/normalize.py
docker compose run --rm app python scripts/chunk.py
docker compose run --rm app python scripts/embed_chunks.py
```

Order matters:

1. `fetch.py` preserves raw CourtListener payloads under `storage/raw/`
2. `normalize.py` builds normalized `cases`, `clusters`, and `opinions`
3. `chunk.py` creates retrieval chunks from `opinions.clean_text`
4. `embed_chunks.py` builds the FAISS vector index under `storage/faiss/`

Search/debug scripts can then be used after the corpus has been prepared:

```bash
docker compose run --rm app python scripts/search_fts.py "qualified immunity"
docker compose run --rm app python scripts/search_vector.py "when can police search a phone"
docker compose run --rm app python scripts/search_hybrid.py "qualified immunity"
```

---

## How to run scripts?

All scripts that write to runtime storage must be run inside the app container or dev container.

This includes fetch / ingest / chunk / embedding / indexing scripts.

Reason:
the container uses a Docker named volume for `/workspace/storage`, so host-side script execution and container-side script execution do not write to the same physical storage.

Examples:

```bash
docker compose run --rm app python scripts/fetch.py
docker compose run --rm app python scripts/<script_name>.py
```

---

## Deployed demo note

The hosted Render demo does not run these scripts at startup.

For deployment, the prepared SQLite database and FAISS artifacts for the demo corpus are committed to the repository:

```text
storage/sqlite/casebase.db
storage/faiss/chunks.index
storage/faiss/chunks_ids.npy
storage/faiss/chunks_meta.json
```

This keeps the hosted service read-only at startup and avoids requiring a persistent disk or ingestion/indexing job during deployment.

---

## Deferred improvements

### `fetch.py`

Possible future flags, not needed for the first pass:

* `--from-year`
* `--to-year`
* `--court`
* `--opinion-type`
* `--refresh-missing-only`

### `normalize.py`

Possible future improvements, not needed for the current pass:

* replace the current regex-based HTML stripping with a more robust HTML parser
* optionally add `BeautifulSoup` support if the corpus later requires safer HTML-to-text extraction
* revisit whitespace normalization for HTML-derived fallback text if chunking/search quality needs it

### `chunk.py`

Possible future improvements, not needed for the first pass:

* add section-aware chunking instead of leaving `section_hint = NULL`
* replace fixed character overlap with boundary-aware overlap so chunks do not begin mid-word or mid-sentence
* optionally nudge overlap starts to whitespace or sentence boundaries
* revisit chunk sizing heuristics if legal-text retrieval quality suggests different `TARGET` / `HARD_MAX` / `OVERLAP` values
* improve giant-paragraph splitting beyond simple sentence-ish regex splitting
* consider stronger whitespace normalization inside chunk text if snippet quality needs it
* revisit heading / section detection later if reliable structure can be inferred from opinions
* consider a more context-aware legal-text sentence/structure parser if regex heuristics prove too naive for citations, abbreviations, headings, or numbered sections

---

