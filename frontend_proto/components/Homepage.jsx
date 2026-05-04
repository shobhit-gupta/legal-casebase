/* Homepage — search entry + corpus snapshot.
 * Stats block is wired through window.searchApi.getStats() so it lines
 * up with the documented GET /stats response shape and swaps to the
 * real backend by setting window.SEARCH_API_BASE.
 */

const StatsCard = () => {
  const [stats, setStats] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;
    window.searchApi.getStats()
      .then((s) => { if (!cancelled) setStats(s); })
      .catch((e) => { if (!cancelled) setError(e); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="stats-card" aria-label="Prototype corpus snapshot">
      <div className="stats-card-head">
        <span className="eyebrow">Corpus</span>
        <span style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-4)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
          snapshot
        </span>
      </div>

      {error && (
        <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-3)" }}>
          stats unavailable
        </div>
      )}

      {!error && (
        <div className="stats-rows">
          <span className="k">Cases</span>
          <span className="v">{stats ? stats.cases.toLocaleString() : "—"}</span>

          <span className="k">Opinions</span>
          <span className="v">{stats ? stats.opinions.toLocaleString() : "—"}</span>

          <span className="k">Chunks indexed</span>
          <span className="v">{stats ? stats.chunks_indexed.toLocaleString() : "—"}</span>

          <span className="div" />

          <span className="k">Court</span>
          <span className="v" style={{ fontSize: 11.5 }}>{stats ? stats.court : "—"}</span>

          <span className="k">Source</span>
          <span className="v" style={{ fontSize: 11.5 }}>{stats ? stats.source : "—"}</span>

          <span className="k">Vector dim</span>
          <span className="v">{stats?.vector_dimension != null ? stats.vector_dimension.toLocaleString() : "—"}</span>

          <span className="k">Embedding</span>
          <span className="v" style={{ fontSize: 11, whiteSpace: "nowrap" }}>
            {stats ? stats.embedding_model : "—"}
          </span>
        </div>
      )}

      <div className="stats-foot" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        GET /stats &nbsp;·&nbsp;
        {stats ? stats.retrieval_modes.join(" · ") : "fts · vector · hybrid"}
      </div>
    </div>
  );
};

const modeLabel = (mode) =>
  mode === "fts" ? "keyword" :
    mode === "vector" ? "semantic" :
      "hybrid";

const ExampleQueries = ({ onPick }) => (
  <section>
    <div className="eyebrow" style={{ marginBottom: 12 }}>Try a query</div>
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {window.EXAMPLE_QUERIES.map((ex) => (
        <li key={ex.q} style={{ borderTop: "1px solid var(--rule-soft)" }}>
          <button
            onClick={() => onPick(ex.q, ex.mode)}
            style={{
              width: "100%",
              textAlign: "left",
              background: "transparent",
              border: 0,
              padding: "12px 0",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 16,
              color: "var(--ink)",
            }}
            onMouseEnter={(e) => e.currentTarget.style.color = "var(--accent)"}
            onMouseLeave={(e) => e.currentTarget.style.color = "var(--ink)"}
          >
            <span style={{ fontFamily: "var(--serif)", fontSize: 16, fontStyle: "italic", textWrap: "pretty" }}>"{ex.q}"</span>
            <span style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-4)", letterSpacing: "0.03em", textTransform: "uppercase", whiteSpace: "nowrap", flexShrink: 0 }}>
              {ex.hint} · {modeLabel(ex.mode)} →
            </span>
          </button>
        </li>
      ))}
      <li style={{ borderTop: "1px solid var(--rule-soft)" }} />
    </ul>
  </section>
);

const Homepage = ({ onSearch }) => {
  const [query, setQuery] = React.useState("");
  const [mode, setMode] = React.useState("hybrid");

  const submit = (q, m) => {
    const finalQ = (q ?? query).trim();
    if (!finalQ) return;
    onSearch(finalQ, m ?? mode);
  };

  return (
    <div style={{ minHeight: "calc(100vh - 56px)", display: "flex", flexDirection: "column" }}>
      <main className="home-main" style={{ flex: 1, maxWidth: 1080, width: "100%", margin: "0 auto", padding: "96px 32px 0" }}>
        {/* Single inner content wrapper — aligns hero, search bar, and lower row */}
        <div style={{ maxWidth: 720, margin: "0 auto" }}>
          <div style={{ marginBottom: 32 }}>
            <div className="eyebrow" style={{ marginBottom: 14 }}>U.S. Supreme Court · CourtListener</div>
            <h1 className="home-h1" style={{
              fontFamily: "var(--serif)",
              fontWeight: 400,
              fontSize: 38,
              lineHeight: 1.18,
              letterSpacing: "-0.012em",
              margin: "0 0 14px",
              color: "var(--ink)",
              textWrap: "pretty",
            }}>
              A small, traceable casebase
              <span style={{ color: "var(--ink-4)" }}> for searching legal opinions.</span>
            </h1>
            <p style={{ color: "var(--ink-3)", fontSize: 15, lineHeight: 1.55, margin: 0, maxWidth: 580, textWrap: "pretty" }}>
              Keyword, semantic, and hybrid retrieval over chunked opinion text. Every result links
              back to its case, opinion, chunk, and character offsets.
            </p>
          </div>

          <div>
            <SearchField
              query={query}
              setQuery={setQuery}
              mode={mode}
              setMode={setMode}
              onSubmit={() => submit()}
              autoFocus
            />

            <div style={{
              display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8,
              marginTop: 10, fontSize: 12, color: "var(--ink-4)",
            }}>
              <div>
                <span className="kbd">/</span> to focus &nbsp;·&nbsp;
                <span className="kbd">⏎</span> to search
              </div>
              <div style={{ fontFamily: "var(--mono)" }}>
                GET /search?mode={mode}
              </div>
            </div>
          </div>

          {/* Examples + corpus stats — share the same 720px inner width */}
          <div className="home-grid">
            <ExampleQueries onPick={(q, m) => submit(q, m)} />
            <StatsCard />
          </div>
        </div>

        {/* About — static, no fake numbers */}
        <section style={{ marginTop: 56, paddingBottom: 64, maxWidth: 680, margin: "56px auto 0" }}>
          <div className="eyebrow" style={{ marginBottom: 12 }}>About this prototype</div>
          <p style={{ color: "var(--ink-3)", fontSize: 13.5, lineHeight: 1.65, margin: 0, textWrap: "pretty" }}>
            Search runs against a normalized SCOTUS slice from CourtListener:
            cases &rarr; opinions &rarr; chunks. Keyword search is SQLite FTS5,
            semantic search is FAISS over OpenAI embeddings, hybrid fuses the
            two with reciprocal rank fusion. Each result returns its
            chunk, opinion, and case identifiers so you can trace any match
            back to the source text.
          </p>
        </section>
      </main>
      <Footer />
    </div>
  );
};

window.Homepage = Homepage;
