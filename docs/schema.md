# Legal Casebase — Working Schema Document

**Version:** v0.3  
**Status:** In Review  
**Purpose:** This is the shared schema working document for Shobhit, ChatGPT, and Claude. It is meant to record:
1. what was explored,
2. what was found,
3. what inferences were drawn,
4. which decisions are locked,
5. which questions remain open, and
6. the current recommended MVP schema.

This document is intentionally structured so future discussion can update only the relevant sections instead of rewriting the whole thing.

---

## 1. Problem We Are Solving

We are building a **mini legal casebase search engine with optional AI-assisted features**.

The product is primarily:
- a searchable legal document system,
- with structured browsing,
- with keyword + semantic retrieval,
- with clear source traceability.

This is **not** a chatbot-first product.

Schema must therefore support:
- a real legal/case hierarchy,
- stable case identity,
- searchable opinion text,
- chunk-based retrieval,
- citation relationships,
- later RAG-style additions without architectural rewrite.

---

## 2. CourtListener Source Hierarchy

Based on REST API docs + real payload exploration, the effective source hierarchy is:

```text
Court
  └── Docket
        └── Cluster
              └── Opinion
                    └── opinions_cited -> Opinion[]
```

### Interpreted roles
- **Docket** = case-level administrative/canonical identity
- **Cluster** = decision event / grouping layer
- **Opinion** = actual text-bearing object
- **Chunk** = retrieval unit derived from opinion text

---

## 3. What We Explored

### 3.1 API surface exploration
We inspected `OPTIONS` metadata for:
- `clusters`
- `opinions`
- `dockets`

This gave us:
- field inventories,
- available filters,
- ordering options,
- relationship directions.

### 3.2 Real payload exploration
We inspected:
- a live `opinions` query for recent SCOTUS records,
- a real opinion payload,
- its parent cluster payload,
- its parent docket payload.

### 3.3 What this changed
This moved the work from **API-shape assumptions** to **data-informed schema reasoning**.

---

## 4. Key Findings From Exploration

### 4.1 Opinion objects are the real text/search anchor
The opinion payload contains the fields that matter most for retrieval:
- `plain_text`
- `html_with_citations`
- `type`
- `per_curiam`
- `page_count`
- `download_url`
- `local_path`
- `opinions_cited`

**Inference:** opinion is the correct unit for text storage, chunking, search, and semantic retrieval.

---

### 4.2 Cluster objects are useful but thin
The cluster payload is useful for:
- `absolute_url`
- `slug`
- `date_filed`
- `judges`
- `precedential_status`
- `sub_opinions`
- linkage upward to docket

But for recent SCOTUS cases, many richer metadata fields are empty:
- `summary`
- `syllabus`
- `headnotes`
- `disposition`
- `history`
- `citations` often empty

**Inference:** cluster is important, but too thin to be the sole canonical case record for the MVP.

---

### 4.3 Docket objects carry the strongest case-level identity
The docket payload adds the best case-level metadata:
- `case_name`
- `case_name_short`
- `absolute_url`
- `slug`
- `docket_number`
- `docket_number_core`
- `date_filed`
- `date_argued`
- `appeal_from_str`
- `audio_files`
- `clusters`
- `court_id`

Most importantly, a docket can contain **multiple clusters**.

**Inference:** docket is the most stable case-level object and should anchor canonical case identity.

---

### 4.4 Recent SCOTUS metadata is sparse
For recent SCOTUS entries, many rich editorial/legal metadata fields are empty or sparse.

**Implication:** schema should not over-assume:
- parallel citations always present,
- summaries/headnotes always present,
- author fields always reliable,
- one clean editorially structured cluster record.

---

### 4.5 Text field strategy is now clear
- Use **`plain_text`** for cleanup, chunking, and FTS indexing.
- Use **`html_with_citations`** for richer detail-page display when available.

**Inference:** keep both fields at the opinion layer.

---

### 4.6 Author fields are not perfectly reliable
- `author_str` may be empty even when authorship is obvious.
- `author_id` may be missing.
- `judges` on cluster is often more usable for display.

**Inference:** keep both raw and normalized author-related fields; do not over-trust any single source field.

---

### 4.7 Citation graph is viable for MVP
`opinions_cited` provides a useful opinion-to-opinion edge list.

**Inference:** MVP does not need the dedicated citation API before it can support a useful citation graph / related cases feature.

---

## 5. Locked Decisions

These decisions are now treated as settled unless new evidence directly contradicts them.

### 5.1 Canonical case-level object
**Locked:** `docket`

Reason:
- richer case-level metadata,
- stable identity,
- supports multiple clusters per case.

### 5.2 Canonical text/search object
**Locked:** `opinion`

Reason:
- contains the actual text,
- best place for chunking and retrieval,
- carries `opinions_cited`.

### 5.3 Cluster role
**Locked:** thin linking/enrichment layer

Reason:
- useful for decision-level metadata,
- not rich enough to be the canonical case record,
- still important between docket and opinion.

### 5.4 Retrieval unit
**Locked:** `chunk`

Reason:
- required for hybrid retrieval,
- supports FTS5 + FAISS,
- future RAG layer will naturally operate on chunks.

### 5.5 Text field usage
**Locked:**
- `plain_text` for cleanup/chunking/indexing
- `html_with_citations` for display

### 5.6 Raw preservation strategy
**Locked for MVP:** raw JSON files on disk under `data/raw/`

Reason:
- simplest sprint-friendly protection against normalization mistakes,
- zero schema overhead,
- easy to inspect manually,
- enough for re-normalization if schema changes during the sprint.

Note:
- raw SQLite tables remain a valid future upgrade if re-normalization becomes more frequent or DB-only auditability becomes important.

### 5.7 Cluster normalization existence
**Locked:** keep a normalized `clusters` table

Reason:
- cluster is a real first-class source object,
- it links cases to opinions,
- it carries useful decision-level fields like `date_filed`, `judges`, `precedential_status`, `slug`, and `absolute_url`.

What remains open is **how thin or rich** this table should be, not whether it should exist.

### 5.8 Normalization-first policy for MVP
**Locked:** build the MVP against the intact logical model first, and treat broader denormalization as a later optimization.

Allowed from the start:
- small, explicit denormalizations that are easy to justify (for example, `chunks.case_id` for result assembly).

Deferred until evidence exists:
- copying broad docket/cluster metadata onto `opinions` just for convenience.

Reason:
- preserves a clean source-faithful model,
- makes performance and complexity tradeoffs measurable,
- avoids premature schema drift.

---

## 6. Open Decisions

These are still open and should be discussed explicitly when revising the schema.

### 6.1 Citation scope
**Status:** Open

Question:
Should citations only store edges between opinions we have ingested, or also preserve references to out-of-corpus cases?

**Current leaning:** support out-of-corpus references via nullable target IDs + raw reference fields.

Reason:
- preserves traceability,
- avoids silently dropping legal references outside the local corpus.

---

### 6.2 Cluster normalization depth
**Status:** Open, leaning thin table

Question:
Given that a normalized `clusters` table is now settled, how much should it contain for MVP?

**Current leaning:** keep it thin.

Reason:
- recent SCOTUS cluster payloads are sparse,
- cluster is important as a linking/enrichment layer,
- richer normalization can be added later if older or more metadata-rich slices justify it.

---

### 6.3 Multiple substantive clusters per docket
**Status:** Open factual question

Question:
How often does one target-case docket have multiple substantive clusters in the chosen SCOTUS slice?

Why this matters:
- if common, docket-first design is strongly validated,
- if rare, the distinction still matters conceptually but less for MVP complexity.

---

### 6.4 Section labeling strategy in chunks
**Status:** Open

Question:
How should `section_hint` be represented when chunking opinions?

Possible approaches:
- simple labels: `Syllabus`, `Opinion`, `Dissent`
- richer labels: `Opinion of the Court / I / A`
- include opinion type + section marker together

**Current leaning:** keep section hints simple at first, enrich later only if needed.

---

### 6.5 Opinion-level blocked/privacy field
**Status:** Open factual question

Question:
Does the opinion object itself expose a `blocked` or equivalent privacy flag in the target slice?

Current evidence:
- `blocked` was seen on cluster and docket payloads.
- It has **not yet been confirmed** on the real opinion payloads we inspected.

**Current leaning:** do not add an `opinions.blocked` field until it is verified in actual opinion data or official endpoint metadata.

---

### 6.6 Flat opinion model enriched with docket/cluster fields
**Status:** Evaluated, not adopted as base schema

Question:
Should we collapse the MVP into a largely opinion-flat model and copy key docket/cluster fields onto opinions from the start?

**Current decision:** not as the base model.

Reason:
- the logical model is now clear enough to implement directly,
- denormalizing broadly from the start would make it harder to measure whether it truly helps,
- case-level identity and opinion-level text are genuinely distinct concepts in the source model.

**Allowed interpretation:** targeted denormalization may still be added later if a real performance or implementation pain point appears.

---

## 7. Current Recommended MVP Schema

This is the **current recommended baseline**, not a forever schema.

### 7.1 `cases`
One row per docket.

Suggested fields:
- `id` (internal PK)
- `source_docket_id`
- `court_id`
- `absolute_url`
- `slug`
- `case_name`
- `case_name_short`
- `docket_number`
- `docket_number_core`
- `docket_number_raw`
- `date_filed`
- `date_argued`
- `appeal_from_str`
- `originating_docket_number`
- `has_audio`
- `blocked`
- `date_ingested`

---

### 7.2 `clusters`
Thin normalized linking/enrichment table.

Suggested fields:
- `id` (internal PK)
- `source_cluster_id`
- `case_id` -> `cases.id`
- `absolute_url`
- `slug`
- `case_name`
- `case_name_short`
- `date_filed`
- `judges`
- `precedential_status`
- `citation_count`
- `source_code`
- `blocked`
- `date_ingested`

---

### 7.3 `opinions`
One row per opinion.

Suggested fields:
- `id` (internal PK)
- `source_opinion_id`
- `case_id` -> `cases.id`
- `cluster_id` -> `clusters.id`
- `absolute_url`
- `opinion_type`
- `author_id` nullable
- `author_str`
- `author_display`
- `per_curiam`
- `page_count`
- `download_url`
- `local_path`
- `plain_text`
- `html_with_citations`
- `clean_text`
- `text_source`
- `extracted_by_ocr`
- `date_created_source`
- `date_modified_source`
- `date_ingested`

Notes:
- `author_display` can be derived from available fields (`author_str`, cluster `judges`, etc.)
- `clean_text` is the normalized text used for chunking/indexing
- No `blocked` field is included yet because opinion-level support for that field has not been confirmed in the explored payloads

---

### 7.4 `chunks`
Retrieval units derived from opinions.

Suggested fields:
- `id` (internal PK)
- `opinion_id` -> `opinions.id`
- `case_id` -> `cases.id`
- `chunk_index`
- `section_hint`
- `text`
- `char_start`
- `char_end`
- `embedding_model`

Notes:
- `case_id` here is **intentional denormalization** for simpler/faster query assembly during search result building.
- Canonical linkage still remains `chunks -> opinions -> cases`.
- FTS5 should index chunk text (and optionally section hints).
- FAISS should map vectors back to `chunks.id`.

---

### 7.5 `citations`
Opinion-level citation edges.

Suggested fields:
- `id` (internal PK)
- `from_opinion_id` -> `opinions.id`
- `to_opinion_id` nullable -> `opinions.id`
- `to_source_opinion_id` nullable
- `to_source_cluster_id` nullable
- `raw_ref` nullable
- `relation_type`

Reason for nullable targets:
- local corpus may not contain every cited opinion,
- we still want to preserve the reference.

---

## 8. Explicitly Rejected or Deferred

### 8.1 Cluster as canonical `cases` record
**Rejected**

Reason:
real payloads show docket is the stronger canonical case anchor.

### 8.2 Opinion-only flat model with no case/docket layer
**Rejected**

Reason:
loses stable case identity and richer case-level metadata.

### 8.3 Broad opinion flattening with docket/cluster fields from the start
**Deferred / not adopted as base schema**

Reason:
- may be useful later as a targeted optimization,
- not needed to prove the MVP,
- should be justified by evidence rather than done preemptively.

### 8.4 Full heavyweight normalization of every source object now
**Deferred**

Examples:
- people tables
- full court tables
- full parallel citation normalization
- full originating court normalization
- raw JSON tables in SQLite

Reason:
out of scope for MVP.

---

## 9. Recommended Next Verification Steps

1. Measure how often target SCOTUS dockets have multiple substantive clusters.
2. Fetch one cluster with multiple sub-opinions (majority + dissent/concurrence).
3. Compare `plain_text` vs cleaned `html_with_citations` on one or two cases.
4. Verify that `blocked: false` is consistent across the chosen SCOTUS slice and confirm whether opinion-level blocked/privacy fields exist.
5. Lock exact SQL schema after those checks.

---

## 10. Change Log

- **v0.1** — first shared working schema document combining CourtListener exploration, later docket/cluster/opinion findings, and the current reconciled schema direction.
- **v0.2** — locked raw preservation to filesystem snapshots for MVP, clarified intentional chunk denormalization, added blocked/privacy verification as an explicit open question, and updated schema notes accordingly.
- **v0.3** — locked the existence of a normalized `clusters` table while keeping its depth open, added normalization-first policy for MVP, evaluated the enriched flat-opinion model explicitly, and clarified that broad denormalization is deferred until justified by evidence.
