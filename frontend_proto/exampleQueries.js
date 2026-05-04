/* exampleQueries.js — minimal, real-shape-aware constants
 * Most data comes from searchApi. Only thing
 * that lives here is the example-query list shown on the homepage.
 */

const EXAMPLE_QUERIES = [
  { q: "qualified immunity", hint: "legal doctrine", mode: "hybrid" },
  { q: "when can police search a phone", hint: "natural language", mode: "vector" },
  { q: "probable cause", hint: "legal phrase", mode: "fts" },
];

window.EXAMPLE_QUERIES = EXAMPLE_QUERIES;
