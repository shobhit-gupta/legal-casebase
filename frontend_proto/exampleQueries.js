/* exampleQueries.js — minimal, real-shape-aware constants
 * Most data comes from searchApi. Only thing
 * that lives here is the example-query list shown on the homepage.
 */

const EXAMPLE_QUERIES = [
  { q: "potus", hint: "keyword", mode: "hybrid" },
  { q: "qualified immunity", hint: "doctrine", mode: "hybrid" },
  { q: "when can police search a phone", hint: "natural language", mode: "vector" },
];

window.EXAMPLE_QUERIES = EXAMPLE_QUERIES;
