## Deferred improvements

### `fetch.py`

Possible future flags, not needed for the first pass:
- `--from-year`
- `--to-year`
- `--court`
- `--opinion-type`
- `--refresh-missing-only`

### `normalize.py`

Possible future improvements, not needed for the current pass:
- replace the current regex-based HTML stripping with a more robust HTML parser
- optionally add `BeautifulSoup` support if the corpus later requires safer HTML-to-text extraction
- revisit whitespace normalization for HTML-derived fallback text if chunking/search quality needs it

### `chunk.py`

Possible future improvements, not needed for the first pass:
- add section-aware chunking instead of leaving `section_hint = NULL`
- replace fixed character overlap with boundary-aware overlap so chunks do not begin mid-word or mid-sentence
- optionally nudge overlap starts to whitespace or sentence boundaries
- revisit chunk sizing heuristics if legal-text retrieval quality suggests different `TARGET` / `HARD_MAX` / `OVERLAP` values
- improve giant-paragraph splitting beyond simple sentence-ish regex splitting
- consider stronger whitespace normalization inside chunk text if snippet quality needs it
- revisit heading / section detection later if reliable structure can be inferred from opinions
- consider a more context-aware legal-text sentence/structure parser if regex heuristics prove too naive for citations, abbreviations, headings, or numbered sections

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
