# Legal Casebase Prototype — Architecture Decision Document

> Note: This document is currently being updated to reflect the latest CourtListener exploration and schema decisions. Where this document and `docs/schema.md` differ, treat `docs/schema.md` as the more current source of truth.

**Version:** v0.1
**Status:** Draft / In Review
**Audience:** First-time reader, reviewer, and builders
**Purpose:** Explain what we are building, why this design was chosen, what was rejected, and what is still open. This document is meant to be a living architecture baseline that can be revised by me, you, and Claude without changing its overall structure. It is grounded in the original project brief and the later synthesis/discussion we’ve had around architecture, data, deployment, and scope. 

---

## 1. Problem Statement

We are building a **mini legal casebase search engine with optional AI-assisted features**.

The product is primarily:

* a searchable legal document system
* with structured document browsing
* with keyword + semantic retrieval
* with clear source traceability

It is **not** a chatbot-first product.

The prototype must demonstrate:

1. a legal casebase
2. a retrieval/search system
3. optionally, a small grounded AI enhancement

This framing comes directly from the project brief and remains the governing principle for all later decisions. 

---

## 2. What Success Looks Like

A first-time reviewer should understand in 5–10 minutes that this system:

* stores and organizes legal cases in a structured way
* supports both keyword and semantic retrieval
* shows grounded, traceable results tied back to source documents
* could later support RAG-style features without architectural rewrite

The prototype succeeds even if the AI layer is minimal, as long as the casebase and search experience are strong. 

---

## 3. Constraints and Priorities

### Constraints

* Build window: **2–3 days**
* Corpus should be small but credible
* Setup/ops burden should stay low
* The system must be easy to explain in an interview or demo

### Priorities

1. Search quality
2. Source traceability
3. Structured browsing
4. Clean architecture
5. Optional AI later

### Non-goals

* chatbot-first UX
* heavyweight infra
* overengineered ranking systems
* long, fragile data-ingestion work
* building “production-grade” infrastructure before the demo works

These priorities reflect the original brief and the later synthesis discussion.  

---

## 4. Final Decisions

This section records the decisions that are currently locked.

### 4.1 Application Stack

**Decision**

* **Backend:** FastAPI
* **UI:** Jinja2 templates
* **Frontend styling:** minimal CSS or Tailwind CDN
* **No SPA / no React**

**Why chosen**

This stack is fast to build, easy to explain, and keeps focus on retrieval and document presentation instead of frontend complexity.

**Alternatives considered**

* React / SPA frontend

**Why not chosen**

A SPA adds build and state-management overhead without improving the core demo value for this prototype. Both the brief and later synthesis strongly favor a minimal server-rendered UI.  

---

### 4.2 Storage and Search

**Decision**

* **Primary storage:** SQLite
* **Keyword search:** SQLite FTS5
* **Vector search:** FAISS

**Why chosen**

This is the lowest-friction architecture that still gives strong search capability. SQLite keeps setup nearly zero, FTS5 gives built-in keyword search, and FAISS gives a simple dedicated vector layer.

**Alternatives considered**

* PostgreSQL + pgvector
* ChromaDB

**Why not chosen now**

* **PostgreSQL + pgvector** is a reasonable long-term upgrade path, but it adds setup and hosting surface area that is not justified for a 1–2 day sprint.
* **ChromaDB** was considered easier at first glance, but FAISS is the cleaner low-level choice for this prototype.

**Current stance**

For the MVP, the architecture will be **SQLite + FTS5 + FAISS**. Postgres/pgvector remains a future migration option, not the current baseline. This aligns with the synthesized decision record and Claude’s later approval.  

---

### 4.3 Dataset Source

**Decision**

* **Primary dataset source:** CourtListener bulk/public data
* **Primary strategy:** use a narrow, credible subset
* **Fallback:** curated mock corpus if ingestion becomes a time sink

**Why chosen**

CourtListener gives a real legal corpus and is more credible than mock data, while avoiding the paid/restricted complications of other sources.

**Alternatives considered**

* Indian Kanoon
* full mock corpus as the primary path

**Why not chosen as primary**

* **Indian Kanoon** is not preferred as the primary source because the paid API path is not desired.
* **Mock corpus** remains acceptable only as a fallback if real-data ingestion starts hurting momentum.

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

* pure fixed-size chunking

**Why not chosen**

Pure fixed windows are simpler but weaken provenance and make results feel less like a real legal casebase.

**Current stance**

Chunking is section-aware by default, but implemented pragmatically so complexity does not explode when sections vary in length. This resolves the concern about implementation complexity without abandoning the better retrieval strategy.

---

### 4.5 Embeddings

**Decision**

* **Preferred default:** OpenAI `text-embedding-3-small`
* **Fallback:** local sentence-transformers model

**Decision rule**

Use OpenAI if setup is smooth and low-friction. If there is any meaningful friction, switch immediately to local embeddings.

**Why chosen**

OpenAI embeddings are low-cost and easy if the key is ready, but embeddings must not become a blocker for the MVP. The provider should be swappable behind a small interface.

**Alternatives considered**

* local embeddings as the primary default

**Why not chosen as default**

Local remains a clean fallback, but the current preference is to use OpenAI first if setup is straightforward. This reflects your stated preference after the OpenAI-key discussion.

---

### 4.6 Dataset Stop-Loss

**Decision**

Use a **soft milestone-based stop-loss**, not a rigid aggressive timer.

**Rule**

Do not let ingestion consume the project. If a clean, indexable corpus is not coming together quickly enough to preserve momentum, pivot to the mock fallback.

**Why chosen**

This keeps discipline without turning the process into artificial clock-watching.

**Alternatives considered**

* very aggressive timer
* no stop-loss at all

**Why not chosen**

A rigid timer may be unnecessarily constraining, while no stop-loss risks losing the entire sprint to ingestion problems.

This is now a flexible but explicit guardrail. 

---

### 4.7 AI Timing

**Decision**

AI is **not foundational**. It will be added later.

**Why chosen**

The prototype must succeed as a casebase and retrieval system even without AI. At the same time, the architecture must make later RAG-style additions easy.

**Design implication**

The schema and retrieval pipeline should make later additions like grounded summary or “why this matched” straightforward.

This remains fully aligned with the original brief. 

---

### 4.8 Deployment

**Decision**

Deployment is part of the plan and should happen **early, after Phase 2**, not only at the very end.

**Why chosen**

Early deployment improves confidence, exposes environment issues sooner, and produces a live URL earlier in the build.

**Guardrail**

Deployment must not distort the architecture or delay core search quality work. Local functionality still comes first; deployment follows once ingestion/indexing is working.

**Alternatives considered**

* deployment only at the very end
* no hosted deployment

**Why not chosen**

A live hosted demo has clear value, and you explicitly prefer the earlier deployment milestone if it does not cause major issues. Claude’s later recommendation to deploy after Phase 2 is now accepted into the baseline. 

---

## 5. Core Architecture

### 5.1 Data Model

**Status:** Provisional until final schema is locked.

Planned entities:

* `documents`
* `sections`
* `chunks`
* `citations`

Purpose:

* `documents` = canonical case record
* `sections` = structured legal text blocks
* `chunks` = retrieval units for keyword/vector search
* `citations` = casebase relationships

The exact final schema will be locked later once the remaining architecture discussion is fully settled. For now, the structural direction is agreed. 

---

### 5.2 Retrieval Flow

1. obtain and normalize legal documents
2. split documents into sections/chunks
3. index keyword search in FTS5
4. index embeddings in FAISS
5. run keyword and vector retrieval
6. fuse results using RRF
7. render document-grounded search results with snippets and metadata

This is the agreed retrieval shape for the MVP.

---

### 5.3 UI Flow

* `/` → search entry page
* `/search?q=` → results page
* `/documents/{id}` → document detail page

This remains the agreed minimal UI flow. 

---

## 6. Build Plan

### Phase 1 — Dataset

Goal: obtain and normalize a small legal corpus.

### Phase 2 — Ingestion + Indexing

Goal: working local ingestion pipeline, SQLite schema, FTS5, chunking, embeddings, and FAISS.

### Phase 2.5 — Early Deployment

Goal: deploy the working app skeleton after Phase 2 so the project has a live environment early.

### Phase 3 — Search UI

Goal: keyword + semantic + hybrid results with snippets and metadata.

### Phase 4 — Document Detail

Goal: structured full document page with metadata, provenance, and citations/related docs if feasible.

### Phase 5 — Optional AI Enhancement

Goal: grounded summary or “why this matched”.

### Phase 6 — Polish

Goal: UX improvements, empty states, demo readiness.

This sequence reflects the updated decision to bring deployment in earlier while keeping AI later.  

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

This section is meant to preserve momentum under real build conditions.

---

## 8. Current Open Questions

Only unresolved items belong here.

### 8.1 Final Schema Lock

**Status:** open
**Why still open:** you explicitly chose to defer final schema locking until the rest of the architecture converges.

### 8.2 Exact CourtListener Slice

**Status:** open
**Why still open:** CourtListener is chosen, but the exact topical/court slice has not yet been finalized.

### 8.3 Embedding Provider Execution

**Status:** operationally open, strategically settled
**Current leaning:** OpenAI first, local fallback if setup friction appears

---

## 9. Change Log

* **v0.1** — first real filled architecture draft created from the agreed template, with all currently locked decisions filled in and remaining unresolved items marked as open