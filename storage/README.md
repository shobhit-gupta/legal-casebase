# Storage

This directory represents runtime storage locations used by the project.

- `sqlite/` — SQLite database file
- `raw/` — raw source payload snapshots
- `faiss/` — vector index files

In local containerized development, `storage/` is backed by a Docker named volume. Runtime artifacts written by scripts inside the app/dev container are therefore not automatically written into the host repo's `./storage/` directory.

General rule:
- raw payloads and transient runtime files should not be committed
- placeholder files preserve the folder structure
- SQLite sidecar/temp files such as `*.db-wal`, `*.db-shm`, `*.db-journal`, and `*.db-*` should not be committed

Deployment exception:
- the hosted demo intentionally commits the prepared SQLite database and FAISS artifacts:
  - `storage/sqlite/casebase.db`
  - `storage/faiss/chunks.index`
  - `storage/faiss/chunks_ids.npy`
  - `storage/faiss/chunks_meta.json`

These committed artifacts allow the Render demo to run read-only without regenerating the corpus or vector index at startup.