/* searchApi.js
 *
 * Single integration seam. Today this returns canned responses from
 * fixtures/potus.json (and a couple of curated pre-shaped fixtures).
 * Tomorrow, set window.SEARCH_API_BASE = "https://your-host" and the
 * mock branch is bypassed. The contract here mirrors:
 *
 *   GET /search?query=...&limit=10&mode=fts|vector|hybrid
 *
 * Response shape mirrors app/main.py:
 *   { query, limit, mode, count, results: [...] }
 *
 * Errors mirror tests/test_api.py:
 *   400 — empty query, invalid mode/limit, FTS syntax error
 *   422 — missing query
 *   500 — generic infrastructure
 */

(() => {
  const DEFAULT_LIMIT = 10;
  const VALID_MODES = new Set(["fts", "vector", "hybrid"]);

  // Where to fetch the real API from. Empty string = use mock.
  // To switch to real backend:
  //   window.SEARCH_API_BASE = "http://localhost:8000";
  // and reload.
  window.SEARCH_API_BASE = window.SEARCH_API_BASE || "";

  // ── Mock corpus ─────────────────────────────────────────────
  // Loaded lazily from fixtures/potus.json. Other queries fall back
  // to a re-keyed, mode-respecting subset of those same results so
  // every demo query produces a believable response.
  let _potusCache = null;
  async function _loadPotus() {
    if (_potusCache) return _potusCache;
    const r = await fetch("fixtures/potus.json");
    _potusCache = await r.json();
    return _potusCache;
  }

  function _shapeForMode(rows, mode) {
    // Only the fields actually returned by the backend.
    return rows.map((r, i) => {
      const base = {
        chunk_id:          r.chunk_id,
        chunk_index:       r.chunk_index,
        opinion_id:        r.opinion_id,
        source_opinion_id: r.source_opinion_id,
        case_id:           r.case_id,
        source_docket_id:  r.source_docket_id,
        case_name:         r.case_name,
        docket_number:     r.docket_number,
        char_start:        r.char_start,
        char_end:          r.char_end,
        text:              r.text,
        preview:           r.preview,
      };
      if (mode === "fts") {
        // FTS-only: vector fields null, combined_score null, matched_by="fts"
        return {
          ...base,
          snippet: r.snippet || _fakeSnippet(r.preview, r._query),
          fts_score: r.fts_score ?? -(8 - i * 0.4),
          fts_rank: i + 1,
          vector_score: null, vector_rank: null,
          combined_score: null,
          matched_by: "fts",
        };
      }
      if (mode === "vector") {
        return {
          ...base,
          snippet: null,
          fts_score: null, fts_rank: null,
          vector_score: r.vector_score ?? (0.30 - i * 0.01),
          vector_rank: i + 1,
          combined_score: null,
          matched_by: "vector",
        };
      }
      // hybrid — pass through real shape
      return { ...base, snippet: r.snippet, fts_score: r.fts_score, fts_rank: r.fts_rank,
        vector_score: r.vector_score, vector_rank: r.vector_rank,
        combined_score: r.combined_score, matched_by: r.matched_by };
    });
  }

  function _fakeSnippet(preview, query) {
    if (!query) return preview;
    const terms = query.split(/\s+/).filter(t => t.length > 2);
    let s = preview;
    for (const t of terms) {
      const re = new RegExp(`\\b(${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})\\b`, "ig");
      s = s.replace(re, "[$1]");
    }
    return s;
  }

  // ── Validation (mirrors retrieval.py + main.py) ─────────────
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

  // ── Public API ──────────────────────────────────────────────
  /**
   * search({ query, limit, mode }) → Promise<{query, limit, mode, count, results}>
   *
   * Hits a real backend if window.SEARCH_API_BASE is set,
   * otherwise returns canned data with the same shape.
   */
  async function search({ query, limit = DEFAULT_LIMIT, mode = "hybrid" } = {}) {
    _validate(query, limit, mode);

    if (window.SEARCH_API_BASE) {
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

    // ── Mock branch ────────────────────────────────────────
    const potus = await _loadPotus();
    // Tag rows so the snippet faker can use the query
    const rows = potus.results.map(r => ({ ...r, _query: query }));
    const shaped = _shapeForMode(rows, mode).slice(0, limit);

    // Simulate latency so loading state is visible
    await new Promise(res => setTimeout(res, 380));

    return {
      query, limit, mode,
      count: shaped.length,
      results: shaped,
    };
  }

  // ── Stats ───────────────────────────────────────────────────
  // Mirrors GET /stats. Mock until the backend exposes it; same
  // contract so swapping in window.SEARCH_API_BASE flips it real.
  const STATS_MOCK = {
    cases: 47,
    opinions: 63,
    chunks_indexed: 4218,
    court: "U.S. Supreme Court",
    source: "CourtListener",
    vector_dimension: 1536,
    embedding_model: "text-embedding-3-small",
    retrieval_modes: ["fts", "vector", "hybrid"],
  };

  async function getStats() {
    if (window.SEARCH_API_BASE) {
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
    await new Promise(res => setTimeout(res, 120));
    return STATS_MOCK;
  }

  window.searchApi = { search, getStats };
})();
