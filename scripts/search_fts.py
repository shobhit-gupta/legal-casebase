"""
scripts/search_fts.py

Keyword search over the chunks FTS5 index.

Usage:
    python scripts/search_fts.py "query string" [--limit N]

Notes:
    - multi-word queries must be quoted at the shell level
    - trailing wildcards work: copy*
    - leading wildcards are not supported
    - lower score = better match (bm25 ordering)
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import get_connection

SEARCH_SQL = """
SELECT
    c.id            AS chunk_id,
    c.chunk_index,
    c.opinion_id,
    o.source_opinion_id,
    c.case_id,
    cs.source_docket_id,
    cs.case_name,
    cs.docket_number,
    c.char_start,
    c.char_end,
    bm25(chunks_fts) AS score,
    snippet(chunks_fts, 0, '[', ']', ' \u2026 ', 12) AS snippet
FROM chunks_fts
JOIN chunks   c  ON c.id = chunks_fts.rowid
JOIN opinions o  ON o.id = c.opinion_id
JOIN cases    cs ON cs.id = c.case_id
WHERE chunks_fts MATCH ?
ORDER BY score ASC, c.id ASC
LIMIT ?
"""


def search(query: str, limit: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        try:
            return conn.execute(SEARCH_SQL, (query, limit)).fetchall()
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            looks_like_bad_query = any(
                token in msg
                for token in (
                    "fts5",
                    "match",
                    "syntax",
                    "unterminated string",
                    "parse error",
                    "malformed",
                )
            )
            if looks_like_bad_query:
                print(f"Error: invalid FTS query — {e}", file=sys.stderr)
                print(
                    "Hint: multi-word queries must be quoted at the shell level.\n"
                    "      Trailing wildcards work (copy*); leading wildcards do not.",
                    file=sys.stderr,
                )
                sys.exit(1)
            raise


def print_results(query: str, rows: list[sqlite3.Row]) -> None:
    print(f'Query: "{query}"')

    if not rows:
        print(f'No results found for query: "{query}"')
        return

    print(f"Hits:  {len(rows)}")

    for i, row in enumerate(rows, start=1):
        docket = row["docket_number"] or "—"
        print(f"\n{i}. {row['case_name']} ({docket})")
        print(
            f"   chunk_id={row['chunk_id']}"
            f"  opinion_id={row['opinion_id']}"
            f"  case_id={row['case_id']}"
            f"  source_docket_id={row['source_docket_id']}"
        )
        print(
            f"   opinion={row['source_opinion_id']}"
            f"  chunk={row['chunk_index']}"
            f"  score={row['score']:.4f}"
            f"  chars={row['char_start']}:{row['char_end']}"
        )
        print(f"   {row['snippet']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keyword search over the legal casebase FTS index."
    )
    parser.add_argument("query", help="FTS5 query string")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results to return (default: 10)",
    )
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be greater than 0")
    return args


def main() -> None:
    args = parse_args()
    rows = search(args.query, args.limit)
    print_results(args.query, rows)


if __name__ == "__main__":
    main()
