## Deferred fetcher options

Possible future flags, not needed for the first pass:
- `--from-year`
- `--to-year`
- `--court`
- `--opinion-type`
- `--refresh-missing-only`

## Deferred normalization / text-cleaning improvements

Possible future improvements, not needed for the current pass:
- replace the current regex-based HTML stripping with a more robust HTML parser
- optionally add `BeautifulSoup` support if the corpus later requires safer HTML-to-text extraction
- revisit whitespace normalization for HTML-derived fallback text if chunking/search quality needs it

## Execution rule

All scripts that write to runtime storage must be run inside the app container or dev container.

This includes fetch / ingest / chunk / embedding / indexing scripts.

Reason:
the container uses a Docker named volume for `/workspace/storage`, so host-side script execution and container-side script execution do not write to the same physical storage.

Examples:

```bash
docker compose run --rm app python scripts/fetch.py
docker compose run --rm app python scripts/<script_name>.py

















