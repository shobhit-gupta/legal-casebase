PRAGMA foreign_keys = ON;

/*
Legal Casebase MVP schema

Source model:
  Docket -> Cluster -> Opinion -> Chunk
  opinions_cited -> Opinion[]

This schema is intentionally lean:
- keep the real source hierarchy intact
- keep provenance that supports identity, traceability,
  and ingestion correctness
- defer broader denormalization and speculative indexes
*/


/*
1) cases

Canonical case-level identity, one row per docket.

In this project, `cases` is our normalized case-level table built from
CourtListener docket records. A "case" here is therefore anchored on the
source docket object, not on a cluster or an opinion.

Why these fields are kept:
Stable source identity and traceability:
  source_docket_id, absolute_url, slug, and docket_number

Display:
  case_name and case_name_short

Legal context:
  date_filed, date_argued, appeal_from_str, and originating_docket_number

Ingestion safety:
  blocked

Local provenance/debugging:
  date_ingested
*/
CREATE TABLE IF NOT EXISTS cases (
    id                        INTEGER PRIMARY KEY,
    source_docket_id          INTEGER NOT NULL UNIQUE,
    court_id                  TEXT NOT NULL,
    absolute_url              TEXT,
    slug                      TEXT,
    case_name                 TEXT NOT NULL,
    case_name_short           TEXT,
    docket_number             TEXT,
    date_filed                TEXT,   -- ISO date string if present
    date_argued               TEXT,   -- ISO date string if present
    appeal_from_str           TEXT,
    originating_docket_number TEXT,
    has_audio                 INTEGER NOT NULL DEFAULT 0 CHECK (has_audio IN (0, 1)),
    blocked                   INTEGER NOT NULL DEFAULT 0 CHECK (blocked IN (0, 1)),  -- CourtListener safety flag; blocked records should not be surfaced normally
    date_ingested             TEXT NOT NULL                           -- when this local record was stored/normalized
);

/*
The UNIQUE constraint on source_docket_id already gives us the
only index we clearly need on cases from day one.
*/


/*
2) clusters

Thin decision-event linking/enrichment layer.

Why these fields are kept:
Stable source identity and traceability:
  source_cluster_id, absolute_url, and slug

Hierarchy:
  case_id links each cluster back to the canonical case

Decision-level fields we actually observed:
  case_name, date_filed, judges, and precedential_status

Lightweight source provenance:
  source_code

Ingestion safety:
  blocked
*/
CREATE TABLE IF NOT EXISTS clusters (
    id                  INTEGER PRIMARY KEY,
    source_cluster_id   INTEGER NOT NULL UNIQUE,
    case_id             INTEGER NOT NULL,
    absolute_url        TEXT,
    slug                TEXT,
    case_name           TEXT,
    date_filed          TEXT,
    judges              TEXT,
    precedential_status TEXT,
    source_code         TEXT,                                         -- CourtListener source/provenance code, not raw JSON
    blocked             INTEGER NOT NULL DEFAULT 0 CHECK (blocked IN (0, 1)),
    date_ingested       TEXT NOT NULL,                                -- when this local record was stored/normalized
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
);

/*
Keep this index because the app will routinely fetch clusters
by case, and foreign-key columns do not get indexed automatically.
*/
CREATE INDEX IF NOT EXISTS idx_clusters_case_id ON clusters(case_id);


/*
3) opinions

Text-bearing records; main search/chunking source.

Why these fields are kept:
Stable source identity and traceability:
  source_opinion_id and absolute_url

Hierarchy:
  case_id and cluster_id preserve the source model

Display:
  author_id, author_str, author_display, per_curiam, and page_count

Source access:
  download_url

Text preservation:
  plain_text and html_with_citations are both kept because the corpus
  does not populate them consistently

Retrieval:
  clean_text is the normalized text actually used for chunking
  text_source records which field produced clean_text

Ingestion sanity:
  sha1

Local provenance/debugging:
  date_ingested
*/
CREATE TABLE IF NOT EXISTS opinions (
    id                    INTEGER PRIMARY KEY,
    source_opinion_id     INTEGER NOT NULL UNIQUE,
    case_id               INTEGER NOT NULL,
    cluster_id            INTEGER NOT NULL,
    absolute_url          TEXT,
    opinion_type          TEXT,
    author_id             INTEGER,
    author_str            TEXT,
    author_display        TEXT,
    per_curiam            INTEGER NOT NULL DEFAULT 0 CHECK (per_curiam IN (0, 1)),
    page_count            INTEGER,
    download_url          TEXT,
    sha1                  TEXT,
    plain_text            TEXT,
    html_with_citations   TEXT,
    clean_text            TEXT NOT NULL,
    text_source           TEXT NOT NULL CHECK (
                              text_source IN ('plain_text', 'html_with_citations', 'html')
                           ),                                           -- which source field produced clean_text
    extracted_by_ocr      INTEGER NOT NULL DEFAULT 0 CHECK (extracted_by_ocr IN (0, 1)),
    date_ingested         TEXT NOT NULL,                                -- when this local record was stored/normalized
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY (cluster_id) REFERENCES clusters(id) ON DELETE CASCADE
);

/*
Keep these because the app will regularly traverse opinions
from both cases and clusters.
*/
CREATE INDEX IF NOT EXISTS idx_opinions_case_id ON opinions(case_id);
CREATE INDEX IF NOT EXISTS idx_opinions_cluster_id ON opinions(cluster_id);


/*
4) chunks

Retrieval units derived from opinions.

Why these fields are kept:
Hierarchy:
  opinion_id is the canonical parent

Intentional denormalization:
  case_id supports simpler result assembly

Structure:
  section_hint preserves structure where available

Retrieval:
  text, char_start, and char_end preserve the chunk and its location

Embedding workflow:
  embedding_model stays nullable because chunking may happen
  before embedding generation
*/
CREATE TABLE IF NOT EXISTS chunks (
    id               INTEGER PRIMARY KEY,
    opinion_id       INTEGER NOT NULL,
    case_id          INTEGER NOT NULL,   -- intentional denormalization; copied from the parent case for simpler result assembly
    chunk_index      INTEGER NOT NULL,
    section_hint     TEXT,
    text             TEXT NOT NULL,
    char_start       INTEGER,
    char_end         INTEGER,
    embedding_model  TEXT,               -- nullable: chunking may happen before embedding
    FOREIGN KEY (opinion_id) REFERENCES opinions(id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    UNIQUE (opinion_id, chunk_index)
);

/*
Keep these because retrieval and result assembly will constantly
walk from chunks back to opinions and cases.
*/
CREATE INDEX IF NOT EXISTS idx_chunks_opinion_id ON chunks(opinion_id);
CREATE INDEX IF NOT EXISTS idx_chunks_case_id ON chunks(case_id);


/*
5) FTS5 over chunks

This is the actual keyword-search index for the MVP.
Keep it in sync via normal INSERT/UPDATE/DELETE on chunks.

If needed, rebuild with:
  INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild');
*/
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    section_hint,
    content='chunks',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text, section_hint)
  VALUES (new.id, new.text, new.section_hint);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, section_hint)
  VALUES ('delete', old.id, old.text, old.section_hint);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, section_hint)
  VALUES ('delete', old.id, old.text, old.section_hint);
  INSERT INTO chunks_fts(rowid, text, section_hint)
  VALUES (new.id, new.text, new.section_hint);
END;


/*
6) citations

Opinion-level citation edges.

Why these fields are kept:
In-corpus edges:
  from_opinion_id and to_opinion_id

Out-of-corpus traceability:
  to_source_opinion_id, to_source_cluster_id, and raw_ref

Citation provenance:
  relation_type leaves room for both opinions_cited imports
  and future parsed-inline citations
*/
CREATE TABLE IF NOT EXISTS citations (
    id                    INTEGER PRIMARY KEY,
    from_opinion_id       INTEGER NOT NULL,
    to_opinion_id         INTEGER,
    to_source_opinion_id  INTEGER,
    to_source_cluster_id  INTEGER,
    raw_ref               TEXT,
    relation_type         TEXT NOT NULL CHECK (
                              relation_type IN ('opinions_cited', 'parsed_inline')
                           ),
    FOREIGN KEY (from_opinion_id) REFERENCES opinions(id) ON DELETE CASCADE,
    FOREIGN KEY (to_opinion_id) REFERENCES opinions(id) ON DELETE SET NULL
);

/*
Keep these because citation traversal is a core relation the app
is likely to use immediately for related-opinion features.
*/
CREATE INDEX IF NOT EXISTS idx_citations_from_opinion_id ON citations(from_opinion_id);
CREATE INDEX IF NOT EXISTS idx_citations_to_opinion_id ON citations(to_opinion_id);
