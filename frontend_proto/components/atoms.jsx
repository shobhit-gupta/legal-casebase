/* Shared atoms — top bar, footer, search field, helpers */

const Logo = () => (
  <div className="topbar-brand">
    <span className="topbar-brand-mark">L</span>
    <span>Legal Casebase</span>
    <small>v0.2 · prototype</small>
  </div>
);

const Topbar = ({ view, onNavigate }) => (
  <header className="topbar">
    <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
      <a
        href="#/"
        onClick={(e) => { e.preventDefault(); onNavigate("home"); }}
        style={{ color: "inherit" }}
      >
        <Logo />
      </a>
      <nav className="topbar-nav" aria-label="primary">
        <a
          href="#/"
          className={view === "home" ? "active" : ""}
          onClick={(e) => { e.preventDefault(); onNavigate("home"); }}
        >Search</a>
        <a
          href="https://github.com/shobhit-gupta/legal-casebase"
          target="_blank"
          rel="noopener"
          style={{ fontFamily: "var(--mono)", fontSize: 12 }}
        >Repo ↗</a>
      </nav>
    </div>
    <div className="topbar-meta">
      U.S. Supreme Court · CourtListener corpus
    </div>
  </header>
);

const Footer = () => (
  <footer className="footer">
    <div>
      Legal Casebase · prototype
    </div>
    <div>
      FastAPI · SQLite FTS5 · FAISS · text-embedding-3-small
    </div>
  </footer>
);

const MAGNIFIER = (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <circle cx="7" cy="7" r="4.5" />
    <path d="M10.3 10.3 L13.5 13.5" />
  </svg>
);

const SearchField = ({ query, setQuery, mode, setMode, onSubmit, autoFocus, showModes = true, busy = false }) => {
  return (
    <form
      className="search-shell"
      onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
    >
      <div className="search-shell-icon" aria-hidden>{MAGNIFIER}</div>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search the casebase — cases, opinions, doctrines…"
        autoFocus={autoFocus}
        spellCheck={false}
      />
      {showModes && (
        <div className="search-shell-mode" role="tablist" aria-label="retrieval mode">
          {["fts", "vector", "hybrid"].map((m) => (
            <button
              type="button"
              key={m}
              role="tab"
              aria-selected={mode === m}
              className={"mode-btn " + (mode === m ? "active" : "")}
              onClick={() => setMode(m)}
            >{m === "fts" ? "Keyword" : m === "vector" ? "Semantic" : "Hybrid"}</button>
          ))}
        </div>
      )}
      <button type="submit" className="search-shell-submit" disabled={busy}>
        {busy ? "…" : "Search"}
      </button>
    </form>
  );
};

/* Render a snippet with [bracketed] terms (FTS5 snippet() format from
 * app/retrieval.py) as <mark>. Falls back to plain preview. */
const RenderedSnippet = ({ snippet, preview }) => {
  const text = snippet || preview || "";
  if (!snippet) return <>{text}</>;
  const parts = [];
  let i = 0;
  const re = /\[([^\]]+)\]/g;
  let m, key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > i) parts.push(<span key={key++}>{text.slice(i, m.index)}</span>);
    parts.push(<span key={key++} className="hl">{m[1]}</span>);
    i = m.index + m[0].length;
  }
  if (i < text.length) parts.push(<span key={key++}>{text.slice(i)}</span>);
  return <>{parts}</>;
};

const MatchChip = ({ matched_by }) => {
  const cls = matched_by === "both" ? "both" : matched_by === "fts" ? "fts" : "vector";
  const label = matched_by === "both" ? "keyword + semantic"
    : matched_by === "fts" ? "keyword"
    : "semantic";
  return (
    <span className={"match-chip " + cls} title={`matched_by = ${matched_by}`}>
      <span className="match-chip-dot" />{label}
    </span>
  );
};

/* Trim the long CourtListener party-name string to a readable case name.
 * Real data: "Thomas Perttu, Petitioner v. Kyle Brandon Richards"
 * Render:   "Perttu v. Richards"  (with full title shown on hover)
 */
function shortCaseName(full) {
  if (!full) return "";
  // Split on " v. " (CourtListener canonicalizes this)
  const m = full.match(/^(.+?)\s+v\.\s+(.+)$/i);
  if (!m) return full;
  const [, left, right] = m;
  // Strip CourtListener role suffixes like ", Petitioner" / ", et al." / ", President of..."
  const cleanSide = (side) => {
    return side
      .replace(/,\s*(Petitioner|Respondent|Appellant|Appellee|et al\.).*$/i, "")
      .replace(/,\s*(President|Secretary|Attorney General|Director|Administrator)[^,]*,?.*$/i, "")
      .trim();
  };
  // Take the last meaningful name on each side (surname-style).
  const surname = (s) => {
    const cleaned = cleanSide(s);
    // If it's a corporate/government party with commas, keep first phrase.
    if (/(Inc\.|LLC|Corp\.|Service|Department|United States|Postal)/i.test(cleaned)) {
      return cleaned.split(",")[0].trim();
    }
    const parts = cleaned.split(/\s+/);
    return parts[parts.length - 1];
  };
  return `${surname(left)} v. ${surname(right)}`;
}

Object.assign(window, {
  Topbar, Footer, SearchField, RenderedSnippet, MatchChip, MAGNIFIER, Logo, shortCaseName,
});
