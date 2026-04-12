# Legal Casebase

A small, high-signal prototype of a **legal casebase search engine** with optional AI-assisted features.

This project is being built as a **casebase-first** system, not a chatbot-first product.

The goal is to demonstrate:
- structured legal document storage and browsing
- keyword + semantic retrieval
- source traceability
- a clean path to grounded AI features later

## Project intent

This prototype is meant to show how to build:
1. a **legal casebase**
2. a **retrieval/search system**
3. optionally, a **small grounded AI enhancement**

It should feel like:
- **casebase first**
- **search engine second**
- **AI enhancement third**

It should **not** feel like a generic chatbot wrapped around uploaded documents.

## Current data model direction

The current working model is based on CourtListener's source hierarchy:

- **Docket** → canonical case-level object
- **Cluster** → thin linking/enrichment layer
- **Opinion** → text/search anchor
- **Chunk** → retrieval unit

At the MVP level, the system is being designed with a **normalization-first** approach:
- keep the logical source model intact
- denormalize only later if there is a clear performance or implementation reason

## Core features

### MVP
- ingest a small legal corpus
- store case/opinion metadata
- full-text keyword search
- semantic/vector search
- hybrid retrieval
- result snippets with metadata and traceability
- case detail pages

### Later / optional
- grounded case summary
- “why this matched” explanation
- light RAG-style question answering over retrieved material

## Tech stack

Current implementation direction:
- **Backend:** FastAPI
- **Templates/UI:** Jinja2 + minimal CSS
- **Primary storage:** SQLite
- **Keyword search:** SQLite FTS5
- **Vector search:** FAISS
- **Embeddings:** OpenAI embeddings by default if low-friction, otherwise local fallback
- **Containerization:** Docker + Docker Compose + Dev Container support

## Repository structure

Current structure:

```text
legal-casebase/
├── app/                  # FastAPI app and database helper
├── db/                   # Database schema definition
│   └── schema.sql
├── docs/                 # Architecture + schema working docs
├── scripts/              # Fetching, normalization, ingestion, indexing scripts
├── storage/              # Runtime artifacts (DB, raw payloads, vector index)
│   ├── sqlite/
│   ├── raw/
│   └── faiss/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Data source

The current target source is **CourtListener**.

Why:
- real legal opinions
- usable metadata
- opinion text available via API
- cleaner for prototyping than scraping loosely structured public sites

Current exploration has shown that recent SCOTUS material is strong for:
- opinion text
- basic case metadata
- opinion-to-opinion citation links

And weaker for:
- rich cluster summaries/headnotes on recent cases
- some higher-order metadata fields that are sparse in recent decisions

## Search architecture

The search flow is currently planned as:

1. fetch and preserve raw source payloads
2. normalize dockets / clusters / opinions
3. derive `clean_text` using the locked text-source priority
4. chunk opinion text
5. index keyword search in SQLite FTS5
6. generate embeddings for chunks
7. index vectors in FAISS
8. run keyword + semantic retrieval
9. fuse results using hybrid ranking
10. render case-grounded results with metadata and source links

## Documentation

The main design docs live in `docs/`:

- `docs/architecture.md` — architecture decisions, tradeoffs, and build phases
- `docs/schema.md` — CourtListener exploration findings, schema decisions, ingestion rules, and current recommended MVP schema
- `scripts/README.md` — script usage notes and deferred implementation ideas

These docs are intended to be living documents and may evolve as more of the source data is explored.

## Development setup

The project is intended to be developed in a containerized environment.

Typical local workflow:

```bash
# start the dev environment
docker compose up --build

# run a script inside the app container
docker compose run --rm app python scripts/<script_name>.py
```

If using VS Code, the repo also supports Dev Containers.

## Runtime storage note

In containerized development, `/workspace/storage` is backed by a Docker named volume.

This means runtime artifacts written by the app or scripts inside the container are not written into the host repo's `./storage/` directory.

Project rule:
- run all storage-writing scripts inside the app container or dev container
- do not run fetch / ingest / indexing scripts on the host machine

## Current status

This project is now past the initial architecture/schema exploration phase and is entering **Phase 2 — Ingestion + Indexing**.

What is already established:
- repo scaffolding
- containerized dev environment
- CourtListener API exploration
- schema design
- locked MVP SQL schema
- architecture and schema working docs

What comes next:
- build the raw fetch pipeline
- normalize a representative corpus slice into SQLite
- chunk opinion text
- generate embeddings and build FAISS index
- implement search/results UI
- add case detail pages
- optionally add grounded AI features

## Notes on scope

This project is intentionally optimized for:
- clarity
- demo value
- finishability
- architectural honesty

It is **not** trying to be a production-ready legal research platform.

The prototype wins if it is:
- small
- coherent
- believable
- well-explained
- easy to demo

## License / usage

TBD.

## Acknowledgment

This repository is being developed through iterative design, API exploration, schema refinement, and incremental implementation against real CourtListener data.
