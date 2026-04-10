PRAGMA foreign_keys = ON;

-- ==================================================
-- Legal Casebase MVP schema
-- Source model:
--   Docket -> Cluster -> Opinion -> Chunk
--   opinions_cited -> Opinion[]
-- ==================================================

-- --------------------------------------------------
-- 1) cases
-- Canonical case-level identity, one row per docket
-- --------------------------------------------------
CREATE TABLE cases (
    id                        INTEGER PRIMARY KEY,
    source_docket_id          INTEGER NOT NULL UNIQUE,
    court_id                  TEXT NOT NULL,
    absolute_url              TEXT,
    slug                      TEXT,
    case_name                 TEXT NOT NULL,
    case_name_short           TEXT,
    docket_number             TEXT,
    docket_number_core        TEXT,
    docket_number_raw         TEXT,
    date_filed                TEXT,   -- ISO date string if present
    date_argued               TEXT,   -- ISO date string if present
    appeal_from_str           TEXT,
    originating_docket_number TEXT,
    has_audio                 INTEGER NOT NULL DEFAULT 0 CHECK (has_audio IN (0, 1)),
    blocked                   INTEGER NOT NULL DEFAULT 0 CHECK (blocked IN (0, 1)),
    date_ingested             TEXT NOT NULL
);

CREATE INDEX idx_cases_court_id ON cases(court_id);
CREATE INDEX idx_cases_date_filed ON cases(date_filed);
CREATE INDEX idx_cases_date_argued ON cases(date_argued);
CREATE INDEX idx_cases_docket_number ON cases(docket_number);
CREATE INDEX idx_cases_blocked ON cases(blocked);

-- --------------------------------------------------
-- 2) clusters
-- Thin decision-event linking/enrichment layer
-- --------------------------------------------------
CREATE TABLE clusters (
    id                  INTEGER PRIMARY KEY,
    source_cluster_id   INTEGER NOT NULL UNIQUE,
    case_id             INTEGER NOT NULL,
    absolute_url        TEXT,
    slug                TEXT,
    case_name           TEXT,
    case_name_short     TEXT,
    date_filed          TEXT,
    judges              TEXT,
    precedential_status TEXT,
    citation_count      INTEGER,
    source_code         TEXT,
    blocked             INTEGER NOT NULL DEFAULT 0 CHECK (blocked IN (0, 1)),
    date_ingested       TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
);

CREATE INDEX idx_clusters_case_id ON clusters(case_id);
CREATE INDEX idx_clusters_date_filed ON clusters(date_filed);
CREATE INDEX idx_clusters_precedential_status ON clusters(precedential_status);
CREATE INDEX idx_clusters_blocked ON clusters(blocked);

-- --------------------------------------------------
-- 3) opinions
-- Text-bearing records; main search/chunking source
-- --------------------------------------------------
CREATE TABLE opinions (
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
    local_path            TEXT,
    sha1                  TEXT,
    plain_text            TEXT,
    html_with_citations   TEXT,
    clean_text            TEXT NOT NULL,
    text_source           TEXT NOT NULL CHECK (
                              text_source IN ('plain_text', 'html_with_citations', 'html')
                           ),
    extracted_by_ocr      INTEGER NOT NULL DEFAULT 0 CHECK (extracted_by_ocr IN (0, 1)),
    date_created_source   TEXT,
    date_modified_source  TEXT,
    date_ingested         TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY (cluster_id) REFERENCES clusters(id) ON DELETE CASCADE
);

CREATE INDEX idx_opinions_case_id ON opinions(case_id);
CREATE INDEX idx_opinions_cluster_id ON opinions(cluster_id);
CREATE INDEX idx_opinions_type ON opinions(opinion_type);
CREATE INDEX idx_opinions_per_curiam ON opinions(per_curiam);
CREATE INDEX idx_opinions_sha1 ON opinions(sha1);

-- --------------------------------------------------
-- 4) chunks
-- Retrieval units derived from opinions
-- --------------------------------------------------
CREATE TABLE chunks (
    id               INTEGER PRIMARY KEY,
    opinion_id       INTEGER NOT NULL,
    case_id          INTEGER NOT NULL,   -- intentional denormalization
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

CREATE INDEX idx_chunks_opinion_id ON chunks(opinion_id);
CREATE INDEX idx_chunks_case_id ON chunks(case_id);
CREATE INDEX idx_chunks_section_hint ON chunks(section_hint);

-- --------------------------------------------------
-- 5) FTS5 over chunks
-- Keep this in sync via normal INSERT/UPDATE/DELETE on chunks.
-- If needed, rebuild with:
--   INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild');
-- --------------------------------------------------
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text,
    section_hint,
    content='chunks',
    content_rowid='id'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text, section_hint)
  VALUES (new.id, new.text, new.section_hint);
END;

CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, section_hint)
  VALUES ('delete', old.id, old.text, old.section_hint);
END;

CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, section_hint)
  VALUES ('delete', old.id, old.text, old.section_hint);
  INSERT INTO chunks_fts(rowid, text, section_hint)
  VALUES (new.id, new.text, new.section_hint);
END;

-- --------------------------------------------------
-- 6) citations
-- Opinion-level citation edges
-- --------------------------------------------------
CREATE TABLE citations (
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

CREATE INDEX idx_citations_from_opinion_id ON citations(from_opinion_id);
CREATE INDEX idx_citations_to_opinion_id ON citations(to_opinion_id);
CREATE INDEX idx_citations_to_source_opinion_id ON citations(to_source_opinion_id);
CREATE INDEX idx_citations_to_source_cluster_id ON citations(to_source_cluster_id);
CREATE INDEX idx_citations_relation_type ON citations(relation_type);
