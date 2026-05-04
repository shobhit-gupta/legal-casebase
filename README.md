# Legal Casebase

A small, high-signal prototype of a **legal casebase search engine** with optional AI-assisted features.

This project is being built as a **casebase-first** system, not a chatbot-first product.

**License:** Source-available for non-commercial review and evaluation only.

**Live demo:** https://legal-casebase.onrender.com/  
**Repository:** https://github.com/shobhit-gupta/legal-casebase

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

### Implemented demo
- ingest and normalize a small CourtListener / SCOTUS corpus
- store case, cluster, opinion, and chunk metadata
- full-text keyword search with SQLite FTS5
- semantic/vector search with FAISS and OpenAI embeddings
- hybrid retrieval using reciprocal rank fusion
- result snippets with case/opinion/chunk metadata and traceability
- case detail pages with opinion text and source metadata
- deployed FastAPI + static frontend demo

### Later / optional
- case-level result grouping with best-matching passages underneath
- grounded case summary
- “why this matched” explanation
- light RAG-style question answering over retrieved material

## Tech stack

Current implementation direction:
- **Backend:** FastAPI
- **Frontend/UI:** Static React prototype served by FastAPI, with minimal custom CSS
- **Primary storage:** SQLite
- **Keyword search:** SQLite FTS5
- **Vector search:** FAISS
- **Embeddings:** OpenAI embeddings by default if low-friction, otherwise local fallback
- **Containerization:** Docker + Docker Compose + Dev Container support
- **Deployment:** Render

## Repository structure

Current structure:

```text
legal-casebase/
├── app/                  # FastAPI app and database helper
├── db/                   # Database schema definition
│   └── schema.sql
├── docs/                 # Architecture + schema working docs
├── frontend_proto/       # Static React frontend prototype
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

* real legal opinions
* usable metadata
* opinion text available via API
* cleaner for prototyping than scraping loosely structured public sites

Current exploration has shown that recent SCOTUS material is strong for:

* opinion text
* basic case metadata
* opinion-to-opinion citation links

And weaker for:

* rich cluster summaries/headnotes on recent cases
* some higher-order metadata fields that are sparse in recent decisions

## Search architecture

The implemented search flow is:

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

* `docs/architecture.md` — architecture decisions, tradeoffs, and build phases
* `docs/schema.md` — CourtListener exploration findings, schema decisions, ingestion rules, and current recommended MVP schema
* `scripts/README.md` — script usage notes and deferred implementation ideas

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

## Data preparation pipeline

The demo corpus is prepared through a small script pipeline:

```bash
docker compose run --rm app python scripts/fetch.py
docker compose run --rm app python scripts/normalize.py
docker compose run --rm app python scripts/chunk.py
docker compose run --rm app python scripts/embed_chunks.py
```

## Runtime storage note

In containerized development, `/workspace/storage` is backed by a Docker named volume.

This means runtime artifacts written by the app or scripts inside the container are not written into the host repo's `./storage/` directory.

Project rule:

* run all storage-writing scripts inside the app container or dev container
* do not run fetch / ingest / indexing scripts on the host machine

For the deployed demo, a prebuilt SQLite database and FAISS index for the demo corpus are committed to the repository so the Render service can run read-only without regenerating the corpus at startup.

## Current status

The prototype is deployed and demo-ready.

Implemented:

* CourtListener / SCOTUS corpus ingestion and normalization
* SQLite schema for cases, clusters, opinions, chunks, and citations
* paragraph-first chunking over normalized opinion text
* SQLite FTS5 keyword index
* FAISS vector index over OpenAI embeddings
* keyword, vector, and hybrid search endpoints
* case detail endpoint
* static React frontend served by FastAPI
* Docker-based deployment on Render

Known limitations / next improvements:

* search results are currently returned at the chunk level and may show multiple chunks from the same case; production search should group results by case with best-matching passages underneath
* citation table support exists in the schema/API shape, but citation ingestion and richer related-case views are not yet a focus of the demo
* AI features such as grounded summaries and “why this matched” explanations are intentionally deferred

## Notes on scope

This project is intentionally optimized for:

* clarity
* demo value
* finishability
* architectural honesty

It is **not** trying to be a production-ready legal research platform.

The prototype wins if it is:

* small
* coherent
* believable
* well-explained
* easy to demo

## License / usage

This project is source-available for review and non-commercial evaluation only.

The code is licensed under the PolyForm Noncommercial License 1.0.0. Commercial use, production use, resale, incorporation into commercial products, or use by a company for its own product development requires separate written permission from the author.

See `LICENSE` for details.

## Acknowledgment

This repository is being developed through iterative design, API exploration, schema refinement, and incremental implementation against real CourtListener data.



