"""
scripts/normalize.py

Reads raw CourtListener JSON from storage/raw/courtlistener/ and writes
normalized rows into SQLite (cases, clusters, opinions tables).

Does NOT chunk, index FTS, generate embeddings, or touch FAISS.

Usage:
    python scripts/normalize.py

Behavior:
    Full reset / rebuild on every run. Clears existing rows and re-inserts
    from raw files. Raw files are never modified.

Processing order:
    1. dockets  → cases
    2. clusters → clusters  (requires cases)
    3. opinions → opinions  (requires clusters)
"""

import html as html_stdlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import get_connection

RAW_BASE = ROOT / "storage" / "raw" / "courtlistener"
DOCKETS_DIR  = RAW_BASE / "dockets"
CLUSTERS_DIR = RAW_BASE / "clusters"
OPINIONS_DIR = RAW_BASE / "opinions"


# ── Text utilities ─────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities using stdlib only."""
    return html_stdlib.unescape(_TAG_RE.sub(" ", text))


def derive_clean_text(opinion_id: int, opinion: dict) -> tuple[str, str]:
    """
    Derive clean_text and text_source from opinion raw fields.

    Priority:
      1. plain_text if non-empty
      2. html_with_citations if non-empty after stripping
      3. html if non-empty after stripping

    Each HTML branch checks the cleaned result — not just the raw field —
    before returning, so a tag-only source does not produce empty clean_text.

    Raises RuntimeError if no usable text source is found.
    """
    plain = (opinion.get("plain_text") or "").strip()
    if plain:
        return plain, "plain_text"

    hwc = (opinion.get("html_with_citations") or "").strip()
    if hwc:
        cleaned = strip_html(hwc).strip()
        if cleaned:
            return cleaned, "html_with_citations"

    raw_html = (opinion.get("html") or "").strip()
    if raw_html:
        cleaned = strip_html(raw_html).strip()
        if cleaned:
            return cleaned, "html"

    raise RuntimeError(
        f"Opinion {opinion_id}: no usable text in plain_text, "
        "html_with_citations, or html. Cannot normalize."
    )


# ── Normalization passes ───────────────────────────────────────────────────────

def normalize_cases(conn, date_ingested: str) -> dict[int, int]:
    """
    Insert one cases row per docket file.

    Returns:
        source_docket_id -> normalized cases.id
    """
    docket_files = sorted(DOCKETS_DIR.glob("*.json"))
    print(f"Normalizing {len(docket_files)} dockets → cases...")

    docket_id_map: dict[int, int] = {}

    for path in docket_files:
        d = json.loads(path.read_text(encoding="utf-8"))

        source_docket_id = d["id"]
        orig = d.get("original_court_info") or {}
        originating_docket_number = orig.get("docket_number")
        audio_files = d.get("audio_files") or []

        cursor = conn.execute(
            """
            INSERT INTO cases (
                source_docket_id, court_id, absolute_url, slug,
                case_name, case_name_short,
                docket_number,
                appeal_from_str, originating_docket_number,
                date_filed, date_argued,
                has_audio, blocked, date_ingested
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_docket_id,
                d.get("court_id"),
                d.get("absolute_url"),
                d.get("slug"),
                d.get("case_name") or "",
                d.get("case_name_short"),
                d.get("docket_number"),
                d.get("appeal_from_str"),
                originating_docket_number,
                d.get("date_filed"),
                d.get("date_argued"),
                1 if audio_files else 0,
                1 if d.get("blocked") else 0,
                date_ingested,
            ),
        )
        docket_id_map[source_docket_id] = cursor.lastrowid

    print(f"  Inserted {len(docket_id_map)} cases rows.")
    return docket_id_map


def normalize_clusters(
    conn, date_ingested: str, docket_id_map: dict[int, int]
) -> dict[int, tuple[int, int, str | None]]:
    """
    Insert one clusters row per cluster file.

    Returns:
        source_cluster_id -> (normalized clusters.id, normalized case_id, judges)

    judges is carried so opinion normalization can derive author_display
    without rereading cluster files.
    """
    cluster_files = sorted(CLUSTERS_DIR.glob("*.json"))
    print(f"Normalizing {len(cluster_files)} clusters...")

    cluster_id_map: dict[int, tuple[int, int, str | None]] = {}

    for path in cluster_files:
        c = json.loads(path.read_text(encoding="utf-8"))

        source_cluster_id = c["id"]
        source_docket_id = c.get("docket_id")

        case_id = docket_id_map.get(source_docket_id)
        if case_id is None:
            raise RuntimeError(
                f"Cluster {source_cluster_id}: docket {source_docket_id} not found in "
                "normalized cases. Raw corpus may be incomplete."
            )

        judges = (c.get("judges") or "").strip() or None

        cursor = conn.execute(
            """
            INSERT INTO clusters (
                source_cluster_id, case_id, absolute_url, slug,
                case_name, date_filed, judges,
                precedential_status, source_code,
                blocked, date_ingested
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_cluster_id,
                case_id,
                c.get("absolute_url"),
                c.get("slug"),
                c.get("case_name"),
                c.get("date_filed"),
                judges,
                c.get("precedential_status"),
                c.get("source"),
                1 if c.get("blocked") else 0,
                date_ingested,
            ),
        )
        cluster_id_map[source_cluster_id] = (cursor.lastrowid, case_id, judges)

    print(f"  Inserted {len(cluster_id_map)} clusters rows.")
    return cluster_id_map


def normalize_opinions(
    conn,
    date_ingested: str,
    cluster_id_map: dict[int, tuple[int, int, str | None]],
) -> None:
    """
    Insert one opinions row per opinion file.

    Resolves normalized cluster_id, case_id, and judges from cluster_id_map
    in a single lookup — no cluster file rereads.

    Raises RuntimeError on missing parent cluster or no usable text.
    """
    opinion_files = sorted(OPINIONS_DIR.glob("*.json"))
    print(f"Normalizing {len(opinion_files)} opinions...")

    inserted = 0

    for path in opinion_files:
        o = json.loads(path.read_text(encoding="utf-8"))

        source_opinion_id = o["id"]
        source_cluster_id = o.get("cluster_id")

        cluster_row = cluster_id_map.get(source_cluster_id)
        if cluster_row is None:
            raise RuntimeError(
                f"Opinion {source_opinion_id}: cluster {source_cluster_id} not found in "
                "normalized clusters. Raw corpus may be incomplete."
            )

        normalized_cluster_id, case_id, judges = cluster_row

        # author_display: author_str first, then cluster judges, then NULL
        author_str = (o.get("author_str") or "").strip()
        author_display = author_str or judges or None

        clean_text, text_source = derive_clean_text(source_opinion_id, o)

        conn.execute(
            """
            INSERT INTO opinions (
                source_opinion_id, case_id, cluster_id,
                absolute_url, opinion_type,
                author_id, author_str, author_display,
                per_curiam, page_count,
                download_url, sha1,
                plain_text, html_with_citations,
                clean_text, text_source,
                extracted_by_ocr,
                date_ingested
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_opinion_id,
                case_id,
                normalized_cluster_id,
                o.get("absolute_url"),
                o.get("type"),
                o.get("author_id"),
                author_str or None,
                author_display,
                1 if o.get("per_curiam") else 0,
                o.get("page_count"),
                o.get("download_url"),
                o.get("sha1"),
                o.get("plain_text"),
                o.get("html_with_citations"),
                clean_text,
                text_source,
                1 if o.get("extracted_by_ocr") else 0,
                date_ingested,
            ),
        )
        inserted += 1

    print(f"  Inserted {inserted} opinions rows.")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    date_ingested = datetime.now(timezone.utc).isoformat()
    print(f"\nNormalizing corpus — run timestamp: {date_ingested}\n")

    with get_connection() as conn:
        print("Clearing existing normalized rows...")
        conn.execute("DELETE FROM opinions")
        conn.execute("DELETE FROM clusters")
        conn.execute("DELETE FROM cases")
        print("  Done.\n")

        docket_id_map = normalize_cases(conn, date_ingested)
        print()
        cluster_id_map = normalize_clusters(conn, date_ingested, docket_id_map)
        print()
        normalize_opinions(conn, date_ingested, cluster_id_map)

    print("\nNormalization complete.")


if __name__ == "__main__":
    main()
