/* caseApi.js — GET /cases/{case_id} integration
 *
 * Fetches from the same-origin FastAPI backend. window.SEARCH_API_BASE is
 * always set by searchApi.js (defaults to window.location.origin).
 *
 * Backend response shape:
 *   {
 *     case:      { id, court_id, case_name, docket_number, date_filed,
 *                  date_argued, appeal_from_str, absolute_url, ... },
 *     opinions:  [ { id, opinion_type, author_display, clean_text, ... } ],
 *     citations: [ ... ]   // empty array for most current corpus cases
 *   }
 *
 * Opinions are returned by the backend in display order (combined/majority
 * first, dissent last). The frontend defaults to opinions[0].
 */

/* Friendly label for opinion_type codes. The numeric prefix is CourtListener's
 * sort key; we strip it and humanize. */
function opinionTypeLabel(code) {
  if (!code) return "Opinion";
  const stripped = code.replace(/^0\d{2}/, "");
  const map = {
    combined: "Opinion",
    majority: "Majority",
    plurality: "Plurality",
    concurrence: "Concurrence",
    "concurrence-in-part": "Concurrence in part",
    dissent: "Dissent",
    "dissent-in-part": "Dissent in part",
    "concurrence-in-part-and-dissent-in-part": "Concur/Dissent in part",
    seriatim: "Seriatim",
    rehearing: "Rehearing",
    "on-the-merits": "On the merits",
    "in-chambers": "In chambers",
    remittitur: "Remittitur",
  };
  return map[stripped] || stripped.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Opinion";
}

/* Friendly court name for known courts. */
function courtLabel(courtId) {
  const map = {
    scotus: "U.S. Supreme Court",
    ca1: "U.S. Court of Appeals · 1st Cir.",
    ca2: "U.S. Court of Appeals · 2d Cir.",
    ca9: "U.S. Court of Appeals · 9th Cir.",
    cadc: "U.S. Court of Appeals · D.C. Cir.",
  };
  return map[courtId] || courtId || "—";
}

/* Resolved opinion text — picks the populated field per text_source. */
function opinionText(op) {
  if (!op) return "";
  if (op.text_source === "html" && op.clean_text) return op.clean_text;
  if (op.plain_text) return op.plain_text;
  if (op.clean_text) return op.clean_text;
  return "";
}

/* Format ISO date as "Mar 4, 2024". Returns "—" for null/undefined. */
function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

const caseApi = {
  /* Fetch a single case from the backend.
   * Rejects with { status, message } on error (404, 500, network). */
  async fetchCase(case_id) {
    const id = Number(case_id);
    const url = new URL(`/cases/${id}`, window.SEARCH_API_BASE);
    const r = await fetch(url.toString());
    if (!r.ok) {
      const body = await r.json().catch(() => ({ detail: r.statusText }));
      const err = new Error(body.detail || `Case not found (${r.status})`);
      err.status = r.status;
      throw err;
    }
    return r.json();
  },
};

window.caseApi = caseApi;
window.opinionTypeLabel = opinionTypeLabel;
window.courtLabel = courtLabel;
window.opinionText = opinionText;
window.formatDate = formatDate;
