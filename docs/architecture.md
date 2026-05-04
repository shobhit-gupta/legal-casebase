# Legal Casebase Prototype — Architecture Decision Document

**Version:** v0.6  
**Status:** Implemented MVP / In Review  
**Audience:** First-time reader, reviewer, and builders  
**Purpose:** Explain what we are building, why this design was chosen, what was rejected, what is still open, and how the system is expected to evolve during and after the MVP build.

This document is the **architecture baseline**. For exact data-model findings and current schema direction based on CourtListener exploration, see `docs/schema.md`.

---

## 1. Problem Statement

We are building a **mini legal casebase search engine with optional AI-assisted features**.

The product is primarily:

- a searchable legal document system
- with structured document browsing
- with keyword + semantic retrieval
- with clear source traceability

It is **not** a chatbot-first product.

The prototype must demonstrate:

1. a legal casebase
2. a retrieval/search system
3. optionally, a small grounded AI enhancement

This framing remains the governing principle for all decisions in this document.

---

## 2. What Success Looks Like

A first-time reviewer should understand in 5–10 minutes that this system:

- stores and organizes legal cases in a structured way
- supports both keyword and semantic retrieval
- shows grounded, traceable results tied back to source documents
- could later support RAG-style features without architectural rewrite

The prototype succeeds even if the AI layer is minimal, as long as the **casebase and search experience are strong**.

---

## 3. Constraints and Priorities

### Constraints

- Build window: **2–3 days**
- Corpus should be small but credible
- Setup/ops burden should stay low
- The system must be easy to explain in an interview or demo

### Priorities

1. Search quality
2. Source traceability
3. Structured browsing
4. Clean architecture
5. Optional AI later

### Non-goals

- chatbot-first UX
- heavyweight infra
- overengineered ranking systems
- long, fragile data-ingestion work
- building “production-grade” infrastructure before the demo works

---

## 4. Final Decisions

This section records decisions that are currently locked.

### 4.1 Application Stack

**Decision**

- **Backend:** FastAPI
- **UI:** static React prototype served by FastAPI
- **Frontend styling:** minimal custom CSS
- **Frontend build pipeline:** intentionally avoided for the MVP

**Why chosen**

The original architecture favored Jinja2 to avoid frontend complexity. During implementation, the project adopted a small static React prototype because it improved the demo experience while still avoiding a separate frontend build system, package manager, or deployment service.

The current frontend is served directly by FastAPI from `frontend_proto/`. This preserves a simple single-service deployment while allowing a richer search/results/case-detail interface.

**Alternatives considered**

- Jinja2 templates
- full React / Next.js SPA with a build pipeline

**Why not chosen now**

Jinja2 remains simpler, but the static React prototype produced a better demo interface without materially increasing deployment complexity.

A full SPA or Next.js frontend would add build, routing, state-management, and hosting complexity that is not justified for this MVP.

---

### 4.2 Storage and Search

**Decision**

- **Primary storage:** SQLite
- **Keyword search:** SQLite FTS5
- **Vector search:** FAISS

**Why chosen**

This is the lowest-friction architecture that still gives strong search capability. SQLite keeps setup nearly zero, FTS5 gives built-in keyword search, and FAISS provides a simple dedicated vector layer.

**Alternatives considered**

- PostgreSQL + pgvector
- ChromaDB

**Why not chosen now**

- **PostgreSQL + pgvector** is a reasonable long-term upgrade path, but it adds setup and hosting surface area not justified for this sprint.
- **ChromaDB** was considered, but FAISS is the cleaner low-level choice for this prototype.

**Current stance**

For the MVP, the architecture is **SQLite + FTS5 + FAISS**. Postgres/pgvector remains a future migration option, not the current baseline.

---

### 4.3 Dataset Source

**Decision**

- **Primary dataset source:** CourtListener
- **Primary strategy:** use a narrow, credible subset
- **Fallback:** curated mock corpus if ingestion becomes a time sink

**Why chosen**

CourtListener gives a real legal corpus and is more credible than mock data while avoiding the paid/restricted complications of other sources.

**Alternatives considered**

- Indian Kanoon
- full mock corpus as the primary path

**Why not chosen as primary**

- **Indian Kanoon** is not preferred as the primary source because the paid API path is not desired.
- **Mock corpus** remains acceptable only as a fallback if real-data ingestion starts hurting momentum.

**Current stance**

CourtListener is locked as the primary route.

Initial corpus plan:
- **Pass 1:** recent published SCOTUS cases, roughly **50–100 opinions**
- **Pass 2:** a curated set of landmark cases to add recognizability, richer citation structure, and older multi-opinion decision patterns

---

### 4.4 Chunking

**Decision**

Use **paragraph-first chunking** for the implemented MVP:

1. split opinion `clean_text` into paragraph spans
2. group spans into chunks around a target size
3. enforce a hard maximum chunk size
4. use overlapping character windows between chunks
5. set `section_hint = NULL` for now

**Why chosen**

Paragraph-first chunking is simple, deterministic, and sufficient for the deployed prototype. It keeps the retrieval pipeline moving without requiring fragile legal-section parsing across inconsistent source documents.

**Alternatives considered**

- soft section-aware chunking
- pure fixed-size chunking

**Why not chosen now**

Section-aware chunking remains attractive because it can improve provenance and snippet quality, but it is deferred until the source structure can be handled reliably.

Pure fixed windows are simpler but can split legal reasoning awkwardly and weaken readability.

**Current stance**

The implemented MVP uses paragraph-first chunking. Section-aware chunking is a future improvement, not the current baseline.

---

### 4.5 Embeddings

**Decision**

- **Preferred default:** OpenAI `text-embedding-3-small`
- **Fallback:** local sentence-transformers model

**Decision rule**

Use OpenAI if setup is smooth and low-friction. If there is any meaningful friction, switch immediately to local embeddings.

**Why chosen**

OpenAI embeddings are low-cost and easy if the key is ready, but embeddings must not become a blocker for the MVP. The embedding provider should be swappable behind a small interface.

---

### 4.6 Dataset Stop-Loss

**Decision**

Use a **soft milestone-based stop-loss**, not a rigid aggressive timer.

**Rule**

Do not let ingestion consume the project. If a clean, indexable corpus is not coming together quickly enough to preserve momentum, pivot to the mock fallback.

**Why chosen**

This keeps discipline without turning the process into artificial clock-watching.

---

### 4.7 AI Timing

**Decision**

AI is **not foundational**. It will be added later.

**Why chosen**

The prototype must succeed as a casebase and retrieval system even without AI. At the same time, the architecture must make later RAG-style additions easy.

**Design implication**

The schema and retrieval pipeline should make later additions like grounded summary or “why this matched” straightforward.

---

### 4.8 Deployment

**Decision**

The prototype is deployed as a Docker-based FastAPI service on Render.

**Current deployment shape**

- one web service
- FastAPI serves both the API and static frontend
- prebuilt SQLite and FAISS demo artifacts are committed for the hosted demo
- `OPENAI_API_KEY` is provided through Render environment variables
- no ingestion/indexing scripts run during Render startup

**Why chosen**

The hosted demo should start quickly and avoid runtime ingestion/indexing work. Committing the small prebuilt demo artifacts keeps deployment simple and avoids requiring a persistent disk or startup indexing job.

**Guardrail**

This deployment approach is for the demo corpus. For a larger or frequently updated corpus, artifacts should be produced by a proper ingestion/indexing pipeline and deployed through a more durable data storage strategy.

---

### 4.9 Containerization

**Decision**

Use a **containerized dev/runtime setup** from the start.

**Current shape**

- `Dockerfile` + `docker-compose.yml` are required
- one primary app service
- source code is bind-mounted in dev
- runtime artifacts live under `storage/`
- in containerized development, `storage/` is backed by a Docker volume rather than the host repo directory
- `.devcontainer/devcontainer.json` supported for VS Code

**Why chosen**

This reduces environment drift, supports early deployment, and keeps local and hosted execution closer together without introducing unnecessary multi-service complexity.

#### Operational rule

All storage-writing scripts should be run inside the app container or dev container.

Example:

```bash
docker compose run --rm app python scripts/fetch.py
```

Do not run fetch / ingest / indexing scripts on the host.

---

## 5. Core Architecture

### 5.1 Source-Derived Logical Model

Based on CourtListener exploration, the effective source hierarchy is:

```text
Court
  └── Docket
        └── Cluster
              └── Opinion
                    └── opinions_cited -> Opinion[]
```

**Interpreted roles**

* **Docket** = canonical case-level identity
* **Cluster** = thin linking/enrichment layer
* **Opinion** = text-bearing object and search anchor
* **Chunk** = retrieval unit derived from opinion text

This is the source-faithful logical model the MVP is designed around.

---

### 5.2 Data Model Direction

**Status:** schema direction is settled at a high level; exact SQL details live in `docs/schema.md`.

Current planned entities:

* `cases` — canonical case-level records derived from dockets
* `clusters` — thin decision-event linking/enrichment layer
* `opinions` — text-bearing records used for search/chunking
* `chunks` — retrieval units for FTS5 + FAISS
* `citations` — opinion-level citation edges

**Important implementation policy**

The MVP is **normalization-first**:

* preserve the logical source model first
* allow only small, explicit denormalizations where justified
* defer broad flattening/duplication until there is evidence it helps

**Raw preservation**

For MVP safety, raw CourtListener payloads are preserved as JSON snapshots under `storage/raw/` before normalization.

---

### 5.3 Retrieval Flow

1. fetch and preserve raw CourtListener payloads
2. normalize dockets / clusters / opinions
3. clean and chunk opinion text
4. index keyword search in FTS5
5. generate embeddings for chunks
6. index vectors in FAISS
7. run keyword and vector retrieval
8. fuse results using hybrid ranking
9. render case-grounded search results with snippets, metadata, and source links

---

### 5.4 UI and API Flow

The deployed prototype uses FastAPI for both backend APIs and static frontend serving.

**Frontend routes**

* `/` → static frontend entry point
* `#/` → search entry page
* `#/results?q=...&mode=...` → results page
* `#/case/{id}` → case detail page

**Backend API routes**

* `GET /health` → health check
* `GET /stats` → corpus and index metadata
* `GET /search?query=...&mode=...&limit=...` → keyword/vector/hybrid search
* `GET /cases/{id}` → structured case detail payload

The case detail page should feel like a real legal case page, not a generic document view. It shows case-level metadata, linked opinions, opinion text, source traceability, and citation placeholders where available.

---

## 6. Build Sequence / Current Implementation State

### Phase 1 — Dataset Exploration + Corpus Selection

**Status:** complete

Goal:

* inspect real CourtListener data
* choose a narrow slice
* confirm viable fields for the MVP

### Phase 2 — Ingestion + Indexing

**Status:** complete for the current demo corpus

Goal:

* working local ingestion pipeline
* raw payload preservation
* SQLite schema
* FTS5 indexing
* chunking
* embeddings
* FAISS index

### Phase 2.5 — Early Deployment

**Status:** complete

Goal:

* deploy the working app skeleton after Phase 2 so the project has a live environment early

### Phase 3 — Search UI

**Status:** implemented as a static React prototype

Goal:

* keyword + semantic + hybrid results
* snippets + metadata
* traceable result cards

### Phase 4 — Case Detail

**Status:** implemented for current case/opinion payloads

Goal:

* structured case page
* metadata + provenance
* linked opinions
* citations / related docs if feasible

### Phase 5 — Optional AI Enhancement

**Status:** deferred

Goal:

* grounded summary or “why this matched”

### Phase 6 — Polish

**Status:** ongoing

Goal:

* UX improvements
* empty states
* demo readiness

---

## 7. Risks and Fallbacks

The highest-risk early build items have now been resolved for the demo corpus. Remaining risks are mostly product polish, scaling, and future corpus expansion.

### Risk: dataset ingestion drags

**Fallback:** pivot to curated mock corpus.

### Risk: OpenAI setup friction

**Fallback:** use local embeddings immediately.

### Risk: hosted demo availability

**Mitigation:** keep the deployed service simple, use prebuilt demo artifacts, and monitor the health endpoint.

### Risk: chunking complexity grows

**Fallback:** keep section-aware chunking as a future improvement, but use paragraph-group or fixed-size chunks instead of forcing perfect parsing.

### Risk: metadata sparsity in recent cases

**Fallback:** choose a better-balanced slice or enrich the corpus with older cases where useful.

---

## 8. Current Open Questions

Only unresolved or future-facing items belong here.

### 8.1 Landmark Expansion Depth

**Status:** open

The deployed demo currently uses a recent SCOTUS-focused corpus. A future pass may add curated landmark cases to improve recognizability, richer citation structure, and older multi-opinion decision patterns.

### 8.2 Citation Ingestion and Related-Case Views

**Status:** partially deferred

The schema includes citation support, and the case detail API includes a `citations` field. Full citation ingestion and richer related-case views are deferred beyond the current demo.

### 8.3 Case-Level Result Grouping

**Status:** open / next improvement

Current search results are returned at the chunk level. Production-style search should group results by case and show the best-matching passages underneath each case.

### 8.4 Section-Aware Chunking

**Status:** deferred

The implemented MVP uses paragraph-first chunking with `section_hint = NULL`. Section-aware chunking remains a future improvement if reliable heading/section detection becomes worthwhile.

---

## 9. Relationship to `docs/schema.md`

This document defines the **architectural direction**.

`docs/schema.md` is the more detailed source for:

* CourtListener exploration findings
* locked schema decisions
* open schema questions
* current recommended MVP schema

If this document and `docs/schema.md` ever diverge temporarily, treat `docs/schema.md` as the more current source of truth for data-model specifics.

---

## 10. Change Log

* **v0.1** — first real filled architecture draft created from the agreed template, with all currently locked decisions filled in and remaining unresolved items marked as open.
* **v0.2** — updated the architecture to reflect the newer CourtListener-driven model: docket as canonical case identity, cluster as thin linking layer, opinion as text/search anchor, chunk as retrieval unit; aligned UI flow and build plan with the current schema direction; added containerization as a locked architectural decision; clarified that exact SQL/schema details live in `docs/schema.md`.
* **v0.3** — updated storage-path references to match the restructured project layout, including `storage/raw/` for raw payload preservation and `storage/` as the runtime artifact area in containerized development.
* **v0.4** — aligned the containerization section with the current named-volume storage policy, removed duplicated bullets, and clarified that storage-writing scripts must run inside the containerized environment.
* **v0.5** — updated the dataset section to reflect the now-settled CourtListener corpus plan: Pass 1 recent published SCOTUS, followed by a curated landmark-case pass; replaced the stale open question about the exact slice.
* **v0.6** — updated the architecture baseline to reflect the implemented/deployed MVP: static React frontend served by FastAPI, paragraph-first chunking, Render deployment with committed SQLite/FAISS demo artifacts, current API/frontend routing, and updated open questions for post-demo improvements.

