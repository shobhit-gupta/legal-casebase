# Legal Casebase Prototype — Architecture Decision Document

**Version:** v0.2  
**Status:** Draft / In Review  
**Audience:** First-time reader, reviewer, and builders  
**Purpose:** Explain what we are building, why this design was chosen, what was rejected, what is still open, and how the system is expected to evolve during the MVP build.

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
- **UI:** Jinja2 templates
- **Frontend styling:** minimal CSS or Tailwind CDN
- **No SPA / no React**

**Why chosen**

This stack is fast to build, easy to explain, and keeps focus on retrieval and document presentation instead of frontend complexity.

**Alternatives considered**

- React / SPA frontend

**Why not chosen**

A SPA adds build and state-management overhead without improving core demo value for this prototype.

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

CourtListener is locked as the primary route. The exact topical slice remains open.

---

### 4.4 Chunking

**Decision**

Use **soft section-aware chunking**:

1. use headings/sections when detectable
2. otherwise fall back to paragraph-group chunking
3. only then fall back to fixed-size windows

**Why chosen**

This preserves legal structure where possible, produces better snippets, improves traceability, and makes later grounded AI features easier.

**Alternatives considered**

- pure fixed-size chunking

**Why not chosen**

Pure fixed windows are simpler but weaken provenance and make results feel less like a real legal casebase.

**Current stance**

Chunking is section-aware by default, but implemented pragmatically so complexity does not explode when sections vary in length or source structure is inconsistent.

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

Deployment is part of the plan and should happen **early, after Phase 2**, not only at the very end.

**Why chosen**

Early deployment improves confidence, exposes environment issues sooner, and produces a live URL earlier in the build.

**Guardrail**

Deployment must not distort the architecture or delay core search quality work. Local functionality still comes first; deployment follows once ingestion/indexing is working.

---

### 4.9 Containerization

**Decision**

Use a **containerized dev/runtime setup** from the start.

**Current shape**

- `Dockerfile` + `docker-compose.yml` are required
- one primary app service
- bind-mounted source code in dev
- persisted data/index directories outside the image
- `.devcontainer/devcontainer.json` supported for VS Code

**Why chosen**

This reduces environment drift, supports early deployment, and keeps local and hosted execution closer together without introducing unnecessary multi-service complexity.

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

- **Docket** = canonical case-level identity
- **Cluster** = thin linking/enrichment layer
- **Opinion** = text-bearing object and search anchor
- **Chunk** = retrieval unit derived from opinion text

This is the source-faithful logical model the MVP is designed around.

---

### 5.2 Data Model Direction

**Status:** schema direction is settled at a high level; exact SQL details live in `docs/schema.md`.

Current planned entities:

- `cases` — canonical case-level records derived from dockets
- `clusters` — thin decision-event linking/enrichment layer
- `opinions` — text-bearing records used for search/chunking
- `chunks` — retrieval units for FTS5 + FAISS
- `citations` — opinion-level citation edges

**Important implementation policy**

The MVP is **normalization-first**:

- preserve the logical source model first
- allow only small, explicit denormalizations where justified
- defer broad flattening/duplication until there is evidence it helps

**Raw preservation**

For MVP safety, raw CourtListener payloads are preserved as JSON snapshots under `data/raw/` before normalization.

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

### 5.4 UI Flow

- `/` → search entry page
- `/search?q=` → results page
- `/cases/{id}` → case detail page

The case detail page should feel like a real legal case page, not a generic document view. It is expected to show:

- case-level metadata
- one or more linked opinions
- primary opinion text / sections
- source traceability
- citations / related opinions if available

---

## 6. Build Plan

### Phase 1 — Dataset Exploration + Corpus Selection

Goal:
- inspect real CourtListener data
- choose a narrow slice
- confirm viable fields for the MVP

### Phase 2 — Ingestion + Indexing

Goal:
- working local ingestion pipeline
- raw payload preservation
- SQLite schema
- FTS5 indexing
- chunking
- embeddings
- FAISS index

### Phase 2.5 — Early Deployment

Goal:
- deploy the working app skeleton after Phase 2 so the project has a live environment early

### Phase 3 — Search UI

Goal:
- keyword + semantic + hybrid results
- snippets + metadata
- traceable result cards

### Phase 4 — Case Detail

Goal:
- structured case page
- metadata + provenance
- linked opinions
- citations / related docs if feasible

### Phase 5 — Optional AI Enhancement

Goal:
- grounded summary or “why this matched”

### Phase 6 — Polish

Goal:
- UX improvements
- empty states
- demo readiness

---

## 7. Risks and Fallbacks

### Risk: dataset ingestion drags

**Fallback:** pivot to curated mock corpus.

### Risk: OpenAI setup friction

**Fallback:** use local embeddings immediately.

### Risk: deployment friction

**Fallback:** continue locally and push deployment slightly later instead of blocking progress.

### Risk: chunking complexity grows

**Fallback:** keep section-aware as the preferred path, but fall back to paragraph-group or fixed-size chunks instead of forcing perfect parsing.

### Risk: metadata sparsity in recent cases

**Fallback:** choose a better-balanced slice or enrich the corpus with older cases where useful.

---

## 8. Current Open Questions

Only unresolved items belong here.

### 8.1 Exact CourtListener Slice

**Status:** open

**Why still open:** CourtListener is chosen, but the exact topical/court slice has not yet been finalized.

### 8.2 Embedding Provider Execution

**Status:** operationally open, strategically settled

**Current leaning:** OpenAI first, local fallback if setup friction appears.

### 8.3 Cluster Normalization Depth

**Status:** open, leaning thin table

**Why still open:** the existence of a normalized `clusters` table is settled, but the exact depth of cluster normalization for MVP is still under review.

### 8.4 Citation Scope

**Status:** open

**Question:** should citations preserve only in-corpus edges, or also out-of-corpus references?

---

## 9. Relationship to `docs/schema.md`

This document defines the **architectural direction**.

`docs/schema.md` is the more detailed source for:

- CourtListener exploration findings
- locked schema decisions
- open schema questions
- current recommended MVP schema

If this document and `docs/schema.md` ever diverge temporarily, treat `docs/schema.md` as the more current source of truth for data-model specifics.

---

## 10. Change Log

- **v0.1** — first real filled architecture draft created from the agreed template, with all currently locked decisions filled in and remaining unresolved items marked as open.
- **v0.2** — updated the architecture to reflect the newer CourtListener-driven model: docket as canonical case identity, cluster as thin linking layer, opinion as text/search anchor, chunk as retrieval unit; aligned UI flow and build plan with the current schema direction; added containerization as a locked architectural decision; clarified that exact SQL/schema details live in `docs/schema.md`.
