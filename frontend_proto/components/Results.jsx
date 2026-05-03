/* Results — aligned to actual GET /search response shape.
 * No filters, no facets, no invented backend data.
 * Sidebar collapses to a <details> disclosure on narrow screens.
 */

const ModePill = ({ mode }) => (
  <span style={{
    fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.04em",
    textTransform: "uppercase", padding: "2px 7px", border: "1px solid var(--ink)",
    color: "var(--ink)", background: "var(--paper)", borderRadius: 2,
  }}>{mode}</span>
);

const ScoreCell = ({ label, value, rank, dimmed }) => (
  <div style={{
    fontFamily: "var(--mono)",
    fontSize: 11,
    color: dimmed ? "var(--ink-4)" : "var(--ink-2)",
    display: "flex",
    flexDirection: "column",
    gap: 2,
    minWidth: 0,
  }}>
    <span style={{ fontSize: 10, color: "var(--ink-4)", letterSpacing: "0.04em", textTransform: "uppercase" }}>{label}</span>
    <span>
      {dimmed ? "—" : (
        <>
          {value}
          {rank != null && <span style={{ color: "var(--ink-4)" }}>{` · #${rank}`}</span>}
        </>
      )}
    </span>
  </div>
);

const ResultRow = ({ r, idx, showScores, onOpenCase }) => {
  const charLen = r.char_end - r.char_start;
  const display = window.shortCaseName(r.case_name);
  const open = (e) => {
    if (!onOpenCase) return;
    if (e) e.preventDefault();
    onOpenCase(r.case_id);
  };
  return (
    <li
      className="result-row"
      style={{
        padding: "20px 24px 18px",
        borderBottom: "1px solid var(--rule-soft)",
        display: "grid",
        gridTemplateColumns: "32px 1fr",
        gap: 16,
        cursor: onOpenCase ? "pointer" : "default",
      }}
      onClick={(e) => {
        // Don't hijack clicks on links/buttons inside the row.
        if (e.target.closest("a, button")) return;
        open();
      }}
    >
      <div style={{
        fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-4)",
        letterSpacing: "0.02em", paddingTop: 4,
      }}>
        {String(idx + 1).padStart(2, "0")}
      </div>
      <div style={{ minWidth: 0 }}>
        {/* Case heading */}
        <div style={{
          display: "flex", alignItems: "baseline", justifyContent: "space-between",
          gap: 12, marginBottom: 4, flexWrap: "wrap",
        }}>
          <h3 style={{
            margin: 0, fontFamily: "var(--serif)", fontSize: 20, fontWeight: 500,
            letterSpacing: "-0.005em", lineHeight: 1.25, textWrap: "balance",
          }} title={r.case_name}>
            {onOpenCase ? (
              <a
                href={`#/case/${r.case_id}`}
                onClick={open}
                style={{ color: "var(--ink)", textDecoration: "none" }}
              >
                <em style={{ fontStyle: "italic" }}>{display}</em>
              </a>
            ) : (
              <em style={{ fontStyle: "italic", color: "var(--ink)" }}>{display}</em>
            )}
          </h3>
          <MatchChip matched_by={r.matched_by} />
        </div>

        {/* Sub-line: docket + chunk locator (already wraps) */}
        <div style={{
          display: "flex", gap: "6px 14px", alignItems: "center", marginBottom: 12,
          fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-3)",
          letterSpacing: "0.01em", flexWrap: "wrap",
        }}>
          <span>No. {r.docket_number}</span>
          <span style={{ color: "var(--ink-4)" }}>·</span>
          <span>case {r.case_id}</span>
          <span style={{ color: "var(--ink-4)" }}>·</span>
          <span>opinion {r.opinion_id}</span>
          <span style={{ color: "var(--ink-4)" }}>·</span>
          <span>chunk {r.chunk_index}</span>
          <span style={{ color: "var(--ink-4)" }}>·</span>
          <span>chars {r.char_start.toLocaleString()}–{r.char_end.toLocaleString()}</span>
        </div>

        {/* Snippet / preview */}
        <p style={{
          margin: "0 0 14px", fontSize: 14.5, lineHeight: 1.6, color: "var(--ink-2)",
          textWrap: "pretty",
          borderLeft: "2px solid var(--rule)",
          paddingLeft: 14,
        }}>
          <RenderedSnippet snippet={r.snippet} preview={r.preview} />
        </p>

        {/* Traceability strip — wraps on narrow screens */}
        {showScores && (
          <div className="score-strip">
            <ScoreCell label="FTS bm25"   value={r.fts_score?.toFixed(2)}     rank={r.fts_rank}    dimmed={r.fts_score == null} />
            <ScoreCell label="Vector cos" value={r.vector_score?.toFixed(4)}  rank={r.vector_rank} dimmed={r.vector_score == null} />
            <ScoreCell label="RRF"        value={r.combined_score?.toFixed(5)}                    dimmed={r.combined_score == null} />
            <ScoreCell label="Chunk len"  value={`${charLen} ch`} />
            <span className="chunk-id">chunk_id {r.chunk_id}</span>
          </div>
        )}
      </div>
    </li>
  );
};

/* The reusable info content — used both in desktop sidebar and mobile disclosure. */
const InfoContent = ({ mode, query, count }) => (
  <>
    <div style={{ marginBottom: 24 }}>
      <div className="eyebrow" style={{ marginBottom: 10 }}>This query</div>
      <pre style={{
        margin: 0, fontFamily: "var(--mono)", fontSize: 11, lineHeight: 1.7,
        color: "var(--ink-2)", whiteSpace: "pre-wrap", wordBreak: "break-word",
        background: "var(--paper-2)", padding: "10px 12px",
        border: "1px solid var(--rule)",
      }}>
{`GET /search
  query = ${JSON.stringify(query)}
  mode  = ${mode}
  limit = 10

→ ${count} result${count === 1 ? "" : "s"}`}
      </pre>
    </div>

    <div style={{ marginBottom: 22 }}>
      <div className="eyebrow" style={{ marginBottom: 10 }}>Retrieval</div>
      <dl style={{ margin: 0, fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.55 }}>
        <dt style={{ fontWeight: 500, color: "var(--ink)", marginTop: 6 }}>Keyword</dt>
        <dd style={{ margin: "2px 0 0", color: "var(--ink-3)" }}>SQLite FTS5, bm25 ranking</dd>
        <dt style={{ fontWeight: 500, color: "var(--ink)", marginTop: 10 }}>Semantic</dt>
        <dd style={{ margin: "2px 0 0", color: "var(--ink-3)" }}>FAISS, cosine similarity</dd>
        <dt style={{ fontWeight: 500, color: "var(--ink)", marginTop: 10 }}>Hybrid</dt>
        <dd style={{ margin: "2px 0 0", color: "var(--ink-3)" }}>Reciprocal rank fusion (k=60)</dd>
      </dl>
    </div>

    <div>
      <div className="eyebrow" style={{ marginBottom: 10 }}>Match signal</div>
      <ul style={{
        listStyle: "none", padding: 0, margin: 0,
        display: "flex", flexDirection: "column", gap: 6,
        fontSize: 12, color: "var(--ink-3)",
      }}>
        <li><span className="match-chip both">both</span> &nbsp;keyword + semantic</li>
        <li><span className="match-chip fts">fts</span> &nbsp;keyword only</li>
        <li><span className="match-chip vector">vector</span> &nbsp;semantic only</li>
      </ul>
    </div>
  </>
);

const Results = ({ initialQuery, initialMode, onSearch, onOpenCase, showScores = true }) => {
  const [query, setQuery] = React.useState(initialQuery);
  const [mode, setMode] = React.useState(initialMode);
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    setQuery(initialQuery);
    setMode(initialMode);
  }, [initialQuery, initialMode]);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    window.searchApi.search({ query: initialQuery, mode: initialMode, limit: 10 })
      .then((res) => { if (!cancelled) { setData(res); setLoading(false); } })
      .catch((err) => { if (!cancelled) { setError(err); setLoading(false); } });
    return () => { cancelled = true; };
  }, [initialQuery, initialMode]);

  const submit = (q, m) => {
    const finalQ = (q ?? query).trim();
    if (!finalQ) return;
    onSearch(finalQ, m ?? mode);
  };

  const count = data?.count ?? 0;

  return (
    <div style={{ minHeight: "calc(100vh - 56px)", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "20px 24px", borderBottom: "1px solid var(--rule)", background: "var(--paper)" }}>
        <div style={{ maxWidth: 1280, margin: "0 auto" }}>
          <SearchField
            query={query}
            setQuery={setQuery}
            mode={mode}
            setMode={(m) => { setMode(m); submit(query, m); }}
            onSubmit={() => submit()}
            busy={loading}
          />
        </div>
      </div>

      {/* Mobile-only disclosure of the same info that's in the sidebar on desktop */}
      <details className="results-sidebar-mobile">
        <summary>Query · retrieval · legend</summary>
        <div className="inner">
          <InfoContent mode={initialMode} query={initialQuery} count={count} />
        </div>
      </details>

      <div className="results-grid">
        <aside className="results-sidebar">
          <InfoContent mode={initialMode} query={initialQuery} count={count} />
        </aside>

        <main className="results-main">
          <div className="results-header" style={{
            display: "flex", justifyContent: "space-between", alignItems: "baseline",
            paddingBottom: 14, borderBottom: "1px solid var(--rule)", marginBottom: 4,
            gap: 12,
          }}>
            <div style={{ minWidth: 0 }}>
              <div className="eyebrow" style={{ marginBottom: 6 }}>
                {loading ? "searching…" : error ? "error" : `${count} result${count === 1 ? "" : "s"}`}
              </div>
              <h2 style={{
                margin: 0, fontFamily: "var(--serif)", fontWeight: 400,
                fontSize: 22, letterSpacing: "-0.005em", textWrap: "balance",
                wordBreak: "break-word",
              }}>
                Results for <em style={{ fontStyle: "italic" }}>"{initialQuery}"</em>
              </h2>
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexShrink: 0 }}>
              <ModePill mode={initialMode} />
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-4)" }}>limit=10</span>
            </div>
          </div>

          {loading && (
            <div style={{ padding: "60px 0", textAlign: "center", color: "var(--ink-3)", fontFamily: "var(--mono)", fontSize: 12 }}>
              <span className="pulse-bar" /><span className="pulse-bar" /><span className="pulse-bar" />
              <div style={{ marginTop: 8 }}>retrieving</div>
            </div>
          )}

          {error && !loading && (
            <div style={{
              padding: "32px 24px", marginTop: 16,
              border: "1px solid var(--rule)", background: "var(--paper-2)",
            }}>
              <div className="eyebrow" style={{ marginBottom: 8, color: "var(--ink-2)" }}>
                {error.status ? `Error ${error.status}` : "Error"}
              </div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-2)" }}>
                {error.message}
              </div>
            </div>
          )}

          {!loading && !error && data && data.results.length > 0 && (
            <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {data.results.map((r, i) =>
                <ResultRow r={r} idx={i} key={`${r.chunk_id}-${i}`} showScores={showScores} onOpenCase={onOpenCase} />
              )}
            </ol>
          )}

          {!loading && !error && data && data.results.length === 0 && (
            <div style={{ padding: "60px 0", textAlign: "center", color: "var(--ink-3)" }}>
              <p style={{ fontFamily: "var(--serif)", fontSize: 18, fontStyle: "italic", margin: 0 }}>No results.</p>
              <p style={{ fontSize: 13, marginTop: 8 }}>Try a different query or switch retrieval mode.</p>
            </div>
          )}
        </main>
      </div>
      <Footer />
    </div>
  );
};

window.Results = Results;
