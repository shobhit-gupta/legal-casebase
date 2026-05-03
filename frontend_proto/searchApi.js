/* searchApi.js
 *
 * Integration seam for the same-origin FastAPI backend.
 * Defaults to window.location.origin so no configuration is needed when
 * served under /ui/ by the backend. Override window.SEARCH_API_BASE before
 * this script loads to point at a different host.
 *
 * Backend contracts:
 *   GET /search?query=...&limit=10&mode=fts|vector|hybrid
 *     → { query, limit, mode, count, results: [...] }
 *   GET /stats
 *     → { cases, opinions, chunks_indexed, embedding_model, vector_dimension,
 *         court, source, retrieval_modes }
 *
 * Errors:
 *   400 — empty query, invalid mode/limit, FTS syntax error
 *   422 — missing query (framework-level)
 *   500 — generic infrastructure
 */

(() => {
  const DEFAULT_LIMIT = 10;
  const VALID_MODES = new Set(["fts", "vector", "hybrid"]);

  // Defaults to same-origin. Set window.SEARCH_API_BASE before this script
  // loads to override, e.g. window.SEARCH_API_BASE = "https://your-host";
  window.SEARCH_API_BASE = window.SEARCH_API_BASE || window.location.origin;

  // ── Client-side validation (mirrors retrieval.py + main.py) ──
  function _validate(query, limit, mode) {
    if (query == null) {
      const e = new Error("query is required");
      e.status = 422;
      throw e;
    }
    if (!query || !query.trim()) {
      const e = new Error("Query must not be empty or whitespace-only.");
      e.status = 400;
      throw e;
    }
    if (limit <= 0) {
      const e = new Error(`Limit must be > 0, got ${limit}.`);
      e.status = 400;
      throw e;
    }
    if (!VALID_MODES.has(mode)) {
      const e = new Error(`Invalid mode '${mode}'. Must be 'fts', 'vector', or 'hybrid'.`);
      e.status = 400;
      throw e;
    }
  }

  // ── Public API ────────────────────────────────────────────────

  /**
   * search({ query, limit, mode })
   *   → Promise<{ query, limit, mode, count, results }>
   */
  async function search({ query, limit = DEFAULT_LIMIT, mode = "hybrid" } = {}) {
    _validate(query, limit, mode);

    const url = new URL("/search", window.SEARCH_API_BASE);
    url.searchParams.set("query", query);
    url.searchParams.set("limit", String(limit));
    url.searchParams.set("mode", mode);

    const r = await fetch(url.toString());
    if (!r.ok) {
      const body = await r.json().catch(() => ({ detail: r.statusText }));
      const e = new Error(body.detail || `Search failed (${r.status})`);
      e.status = r.status;
      throw e;
    }
    return r.json();
  }

  /**
   * getStats()
   *   → Promise<{ cases, opinions, chunks_indexed, ... }>
   */
  async function getStats() {
    const url = new URL("/stats", window.SEARCH_API_BASE);
    const r = await fetch(url.toString());
    if (!r.ok) {
      const body = await r.json().catch(() => ({ detail: r.statusText }));
      const e = new Error(body.detail || `Stats failed (${r.status})`);
      e.status = r.status;
      throw e;
    }
    return r.json();
  }

  window.searchApi = { search, getStats };
})();
