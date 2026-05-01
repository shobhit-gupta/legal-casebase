/* CaseDetail — renders GET /cases/{case_id} payload.
 *
 * Layout:
 *   Desktop  : meta rail (left, sticky) + reading column (right)
 *   ≤ 960px  : meta collapses above the reading column
 *
 * Identity is paramount. Provenance is compact and monospaced. The reading
 * column uses Source Serif at a comfortable measure. When there is more than
 * one opinion, a quiet pill row appears between identity and reading; for
 * single-opinion cases (the common shape) it does not render at all.
 */

const OPINION_TONE = {
  majority:    { label: "Majority",     tone: "neutral" },
  combined:    { label: "Opinion",      tone: "neutral" },
  plurality:   { label: "Plurality",    tone: "neutral" },
  concurrence: { label: "Concurrence",  tone: "concur"  },
  "concurrence-in-part": { label: "Concurrence in part", tone: "concur" },
  dissent:     { label: "Dissent",      tone: "dissent" },
  "dissent-in-part": { label: "Dissent in part", tone: "dissent" },
  "concurrence-in-part-and-dissent-in-part": { label: "Concur/Dissent", tone: "split" },
  seriatim:    { label: "Seriatim",     tone: "neutral" },
};

function opinionTone(code) {
  if (!code) return { label: "Opinion", tone: "neutral" };
  const stripped = code.replace(/^0\d{2}/, "");
  return OPINION_TONE[stripped] || { label: window.opinionTypeLabel(code), tone: "neutral" };
}

const TONE_STYLE = {
  neutral: { color: "var(--ink-2)",     border: "var(--rule)",        bg: "var(--paper)"   },
  concur:  { color: "var(--signal-vec)", border: "var(--signal-vec)", bg: "var(--signal-vec-bg)" },
  dissent: { color: "var(--signal-fts)", border: "var(--signal-fts)", bg: "var(--signal-fts-bg)" },
  split:   { color: "var(--ink-2)",     border: "var(--rule)",        bg: "var(--paper-2)" },
};

/* ── Pieces ──────────────────────────────────────────────────── */

const MetaRow = ({ k, v, mono = false }) => (
  <>
    <dt style={{
      fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.06em",
      textTransform: "uppercase", color: "var(--ink-4)", margin: 0, paddingTop: 2,
    }}>{k}</dt>
    <dd style={{
      margin: 0, fontFamily: mono ? "var(--mono)" : "var(--sans)",
      fontSize: mono ? 12 : 13, color: "var(--ink)",
      lineHeight: 1.45, wordBreak: "break-word",
    }}>{v ?? <span style={{ color: "var(--ink-4)" }}>—</span>}</dd>
  </>
);

const OpinionPill = ({ op, active, onClick }) => {
  const { label, tone } = opinionTone(op.opinion_type);
  const s = TONE_STYLE[tone];
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        display: "inline-flex", alignItems: "baseline", gap: 8,
        padding: "8px 12px",
        background: active ? "var(--ink)" : s.bg,
        color: active ? "var(--paper)" : s.color,
        border: `1px solid ${active ? "var(--ink)" : s.border}`,
        fontFamily: "var(--sans)", fontSize: 13,
        textAlign: "left", cursor: "pointer", borderRadius: 2,
        minWidth: 0, transition: "background 120ms ease, color 120ms ease",
      }}
    >
      <span style={{
        fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.06em",
        textTransform: "uppercase",
        color: active ? "var(--paper)" : s.color,
        opacity: active ? 0.7 : 1,
      }}>{label}</span>
      <span style={{
        fontFamily: "var(--serif)", fontStyle: "italic", fontWeight: 500,
        fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
      }}>
        {op.per_curiam ? "Per Curiam" : (op.author_display || op.author_str || "—")}
      </span>
      <span style={{
        fontFamily: "var(--mono)", fontSize: 10.5,
        color: active ? "var(--paper)" : "var(--ink-4)",
        opacity: active ? 0.55 : 1, marginLeft: 2,
      }}>{op.page_count}p</span>
    </button>
  );
};

/* Render opinion text as paragraph blocks. We split on blank lines and let
 * SCOTUS-style ALL CAPS section heads render as small smallcaps headings. */
const OpinionBody = ({ text }) => {
  if (!text || !text.trim()) {
    return (
      <p style={{
        fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-4)",
        margin: "20px 0", padding: "16px 18px",
        border: "1px dashed var(--rule)", background: "var(--paper-2)",
      }}>
        No text on file for this opinion. Use the source link to read the original.
      </p>
    );
  }
  const blocks = text.replace(/\r\n/g, "\n").split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, i) => {
        const t = block.trim();
        if (!t) return null;
        // Heading-y if short and mostly CAPS (e.g. "I", "II", section headers).
        const isHead =
          t.length < 80 &&
          /^[IVX]+\.?$/.test(t.replace(/\s+/g, "")) === false
            ? false
            : true;
        const isRoman = /^[IVX]+\.?$/.test(t.replace(/\s+/g, ""));
        if (isRoman) {
          return (
            <h3 key={i} style={{
              fontFamily: "var(--serif)", fontWeight: 500, fontSize: 18,
              letterSpacing: "0.06em", textAlign: "center",
              margin: "32px 0 14px", color: "var(--ink)",
            }}>{t}</h3>
          );
        }
        // Section header heuristic — short, no period at end, looks like a title.
        const isAllCapsHead =
          t.length < 120 &&
          t === t.toUpperCase() &&
          /[A-Z]/.test(t) &&
          !t.endsWith(".") &&
          !t.includes("\n");
        if (isAllCapsHead) {
          return (
            <h4 key={i} style={{
              fontFamily: "var(--mono)", fontSize: 11, fontWeight: 500,
              letterSpacing: "0.1em", textTransform: "uppercase",
              color: "var(--ink-3)", margin: "28px 0 10px",
            }}>{t}</h4>
          );
        }
        // "* * *" centered separator
        if (/^\*+(\s*\*+)*$/.test(t)) {
          return (
            <div key={i} aria-hidden style={{
              textAlign: "center", letterSpacing: "0.5em",
              color: "var(--ink-4)", margin: "24px 0",
            }}>* * *</div>
          );
        }
        return (
          <p key={i} style={{
            margin: "0 0 14px",
            fontFamily: "var(--serif)",
            fontSize: 16.5, lineHeight: 1.65, color: "var(--ink-2)",
            textWrap: "pretty",
          }}>{t}</p>
        );
      })}
    </>
  );
};

/* ── Main component ──────────────────────────────────────────── */

const CaseDetail = ({ caseId, onHome, onBackToResults, lastSearch }) => {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [activeOpId, setActiveOpId] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    window.caseApi.fetchCase(caseId)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setActiveOpId(res.primary_opinion_id);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [caseId]);

  if (loading) {
    return (
      <div className="case-shell">
        <div style={{
          padding: "120px 0", textAlign: "center",
          color: "var(--ink-3)", fontFamily: "var(--mono)", fontSize: 12,
        }}>
          <span className="pulse-bar" /><span className="pulse-bar" /><span className="pulse-bar" />
          <div style={{ marginTop: 8 }}>loading case {caseId}</div>
        </div>
        <Footer />
      </div>
    );
  }

  if (error) {
    return (
      <div className="case-shell">
        <div style={{
          maxWidth: 720, margin: "60px auto", padding: "0 24px",
        }}>
          <div className="eyebrow" style={{ marginBottom: 8, color: "var(--ink-2)" }}>
            {error.status ? `Error ${error.status}` : "Error"}
          </div>
          <h2 style={{ fontFamily: "var(--serif)", fontWeight: 400, margin: "0 0 6px" }}>
            Couldn't load case {caseId}
          </h2>
          <p style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-3)" }}>
            {error.message}
          </p>
          <button
            type="button"
            onClick={onHome}
            style={{
              marginTop: 18, padding: "8px 14px", border: "1px solid var(--ink)",
              background: "var(--paper)", color: "var(--ink)", fontFamily: "var(--sans)",
              fontSize: 13,
            }}
          >← Back to search</button>
        </div>
        <Footer />
      </div>
    );
  }

  const c = data.case;
  const opinions = data.opinions || [];
  const activeOp = opinions.find((o) => o.id === activeOpId) || opinions[0];
  const display = window.shortCaseName(c.case_name);
  const text = window.opinionText(activeOp);
  const wordCount = text ? text.trim().split(/\s+/).length : 0;
  const readMin = wordCount > 0 ? Math.max(1, Math.round(wordCount / 220)) : null;

  return (
    <div className="case-shell">
      {/* Crumb / back affordance */}
      <div style={{
        borderBottom: "1px solid var(--rule)", background: "var(--paper)",
      }}>
        <div className="case-crumb" style={{
          maxWidth: 1280, margin: "0 auto", padding: "12px 32px",
          display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap",
          fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-3)",
          letterSpacing: "0.02em",
        }}>
          {lastSearch ? (
            <a
              href={`#/results?q=${encodeURIComponent(lastSearch.q)}&mode=${lastSearch.mode}`}
              onClick={(e) => { e.preventDefault(); onBackToResults(); }}
              style={{ color: "var(--ink-3)" }}
            >← results for “{lastSearch.q}”</a>
          ) : (
            <a
              href="#/"
              onClick={(e) => { e.preventDefault(); onHome(); }}
              style={{ color: "var(--ink-3)" }}
            >← search</a>
          )}
          <span style={{ color: "var(--ink-4)" }}>·</span>
          <span>{window.courtLabel(c.court_id)}</span>
          <span style={{ color: "var(--ink-4)" }}>·</span>
          <span>No. {c.docket_number}</span>
          <span style={{ color: "var(--ink-4)" }}>·</span>
          <span>case {c.id}</span>
        </div>
      </div>

      {/* Identity header */}
      <div style={{ borderBottom: "1px solid var(--rule)", background: "var(--paper)" }}>
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "28px 32px 24px" }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            {window.courtLabel(c.court_id)} · Docket {c.docket_number}
          </div>
          <h1 style={{
            margin: 0, fontFamily: "var(--serif)", fontWeight: 500,
            fontSize: 32, lineHeight: 1.2, letterSpacing: "-0.01em",
            textWrap: "balance", color: "var(--ink)",
          }}>
            <em style={{ fontStyle: "italic" }}>{display}</em>
          </h1>
          <div
            title={c.case_name}
            style={{
              marginTop: 8, fontFamily: "var(--serif)", fontStyle: "italic",
              fontSize: 15, color: "var(--ink-3)", lineHeight: 1.45,
              maxWidth: 880, textWrap: "pretty",
            }}
          >{c.case_name}</div>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="case-grid">
        <aside className="case-rail">
          <section>
            <div className="eyebrow" style={{ marginBottom: 10 }}>Case</div>
            <dl style={{
              display: "grid", gridTemplateColumns: "auto 1fr",
              columnGap: 14, rowGap: 8, margin: 0,
            }}>
              <MetaRow k="Court"      v={window.courtLabel(c.court_id)} />
              <MetaRow k="Docket"     v={c.docket_number} mono />
              <MetaRow k="Filed"      v={window.formatDate(c.date_filed)} mono />
              <MetaRow k="Argued"     v={window.formatDate(c.date_argued)} mono />
              <MetaRow k="Appeal from" v={c.appeal_from_str} />
              {c.originating_docket_number && (
                <MetaRow k="Below" v={c.originating_docket_number} mono />
              )}
              <MetaRow k="Audio"      v={c.has_audio ? "available at source" : "none"} />
            </dl>
          </section>

          <section style={{ marginTop: 26 }}>
            <div className="eyebrow" style={{ marginBottom: 10 }}>This view</div>
            <pre style={{
              margin: 0, fontFamily: "var(--mono)", fontSize: 11, lineHeight: 1.7,
              color: "var(--ink-2)", whiteSpace: "pre-wrap", wordBreak: "break-word",
              background: "var(--paper-2)", padding: "10px 12px",
              border: "1px solid var(--rule)",
            }}>
{`GET /cases/${c.id}

→ ${opinions.length} opinion${opinions.length === 1 ? "" : "s"}
  primary = ${data.primary_opinion_id}`}
            </pre>
          </section>

          <section style={{ marginTop: 26 }}>
            <div className="eyebrow" style={{ marginBottom: 10 }}>Provenance</div>
            <dl style={{
              display: "grid", gridTemplateColumns: "auto 1fr",
              columnGap: 14, rowGap: 8, margin: 0,
            }}>
              <MetaRow k="Source"    v={`docket ${c.source_docket_id}`} mono />
              <MetaRow k="Slug"      v={c.slug} mono />
              <MetaRow k="Ingested"  v={window.formatDate(c.date_ingested)} mono />
            </dl>
          </section>

          {/* Citations stay quiet until the API actually populates them. */}
          <section style={{ marginTop: 26 }}>
            <div className="eyebrow" style={{ marginBottom: 10 }}>Citations</div>
            {data.citations && data.citations.length > 0 ? (
              <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 12.5 }}>
                {data.citations.map((cit, i) => (
                  <li key={i} style={{ marginBottom: 6, color: "var(--ink-2)" }}>
                    {cit.cite || cit.text || JSON.stringify(cit)}
                  </li>
                ))}
              </ul>
            ) : (
              <p style={{
                margin: 0, fontFamily: "var(--mono)", fontSize: 11.5,
                color: "var(--ink-4)", lineHeight: 1.55,
              }}>
                None linked yet. Cited-by graph will appear here once extracted.
              </p>
            )}
          </section>
        </aside>

        <main className="case-main">
          {/* Opinion switcher — only if >1 */}
          {opinions.length > 1 && (
            <div className="case-opinion-switch" role="tablist" aria-label="Opinions in this case">
              {opinions.map((op) => (
                <OpinionPill
                  key={op.id}
                  op={op}
                  active={op.id === activeOpId}
                  onClick={() => setActiveOpId(op.id)}
                />
              ))}
            </div>
          )}

          {/* Active opinion header */}
          {activeOp && (
            <div className="case-opinion-head">
              <div style={{ minWidth: 0 }}>
                <div className="eyebrow" style={{ marginBottom: 6 }}>
                  {opinionTone(activeOp.opinion_type).label}
                  {activeOp.per_curiam && " · per curiam"}
                  {activeOp.id === data.primary_opinion_id && opinions.length > 1 && " · primary"}
                </div>
                <div style={{
                  fontFamily: "var(--serif)", fontSize: 20, fontWeight: 500,
                  letterSpacing: "-0.005em", color: "var(--ink)",
                }}>
                  {activeOp.per_curiam
                    ? <em style={{ fontStyle: "italic" }}>Per Curiam</em>
                    : <>By <em style={{ fontStyle: "italic" }}>{activeOp.author_display || activeOp.author_str || "Unknown"}</em></>}
                </div>
              </div>
              <div className="case-opinion-meta">
                <span>{activeOp.page_count} pages</span>
                {readMin && <><span className="sep">·</span><span>~{readMin} min read</span></>}
                <span className="sep">·</span>
                <span>text via {activeOp.text_source}{activeOp.extracted_by_ocr ? " (OCR)" : ""}</span>
                {activeOp.download_url && (
                  <>
                    <span className="sep">·</span>
                    <a
                      href={activeOp.download_url}
                      target="_blank"
                      rel="noopener"
                      style={{ color: "var(--accent)" }}
                    >source PDF ↗</a>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Reading column */}
          <article className="case-reader">
            <OpinionBody text={text} />
          </article>

          {/* Foot of opinion: SHA + IDs (technical, small, only here) */}
          {activeOp && (
            <div className="case-opinion-foot">
              <span>opinion {activeOp.id}</span>
              <span className="sep">·</span>
              <span>cluster {activeOp.cluster_id}</span>
              <span className="sep">·</span>
              <span>source {activeOp.source_opinion_id}</span>
              {activeOp.sha1 && (
                <>
                  <span className="sep">·</span>
                  <span title={activeOp.sha1}>sha1 {activeOp.sha1.slice(0, 10)}…</span>
                </>
              )}
            </div>
          )}
        </main>
      </div>

      <Footer />
    </div>
  );
};

window.CaseDetail = CaseDetail;
