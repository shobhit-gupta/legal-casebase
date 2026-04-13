## Deferred fetcher options

Possible future flags, not needed for the first pass:
- `--from-year`
- `--to-year`
- `--court`
- `--opinion-type`
- `--refresh-missing-only`

## Execution rule

All scripts that write to runtime storage must be run inside the app container or dev container.

This includes fetch / ingest / chunk / embedding / indexing scripts.

Reason:
the container uses a Docker named volume for `/workspace/storage`, so host-side script execution and container-side script execution do not write to the same physical storage.

Examples:

```bash
docker compose run --rm app python scripts/fetch.py
docker compose run --rm app python scripts/<script_name>.py