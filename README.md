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
- document detail pages

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

Planned / current structure:

```text
legal-casebase/
├── app/                  # FastAPI app
├── scripts/              # Fetching, normalization, ingestion, indexing scripts
├── data/
│   ├── raw/              # Raw source payload snapshots
│   ├── processed/        # Normalized/intermediate outputs
│   └── casebase.db       # SQLite database
├── index/
│   └── faiss/            # Vector index files
├── docs/
│   ├── architecture.md   # Architecture decision document
│   └── schema.md         # Schema exploration / working schema doc
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
3. clean and chunk opinion text
4. index keyword search in SQLite FTS5
5. generate embeddings for chunks
6. index vectors in FAISS
7. run keyword + semantic retrieval
8. fuse results using hybrid ranking
9. render case-grounded results with metadata and source links

## Documentation

The main design docs live in `docs/`:

- `docs/architecture.md` — architecture decisions, tradeoffs, build phases
- `docs/schema.md` — CourtListener exploration findings, schema decisions, open questions

These docs are intended to be living documents and may evolve as more of the source data is explored.

## Development setup

The project is intended to be developed in a containerized environment.

Typical local workflow:

```bash
# start the dev environment
Docker compose up --build

# run a script inside the app container
Docker compose run app python scripts/<script_name>.py
```

If using VS Code, the repo is also expected to support Dev Containers.

## Current status

This project is still in active design + early implementation.

What is already being established:
- repo scaffolding
- containerized dev environment
- CourtListener API exploration
- schema design
- architecture and documentation baseline

What comes next:
- finalize schema
- ingest a representative corpus slice
- build indexing pipeline
- implement search/results UI
- add document detail page
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

This repository is being developed through iterative design, API exploration, and architecture/schema refinement against real CourtListener data.
