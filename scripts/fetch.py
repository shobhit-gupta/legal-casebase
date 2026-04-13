"""
scripts/fetch.py

Raw data acquisition from CourtListener API.

Fetches SCOTUS dockets, clusters, and opinions and saves them as JSON
under storage/raw/courtlistener/{dockets,clusters,opinions}/.

Usage:
    python scripts/fetch.py [--limit N] [--force] [--sleep SECONDS] [--landmarks]

Options:
    --limit N       Max number of opinions to fetch (default: 100)
    --force         Overwrite existing raw files (default: skip existing)
    --sleep SECONDS Delay between API requests in seconds (default: 0.5)
    --landmarks     Fetch curated landmark cases instead of recent slice
"""

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Literal, TypeAlias

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────

BASE_URL = "https://www.courtlistener.com/api/rest/v4"
TOKEN = os.getenv("COURTLISTENER_TOKEN")

ROOT = Path(__file__).resolve().parents[1]
RAW_BASE = ROOT / "storage" / "raw" / "courtlistener"

DOCKETS_DIR = RAW_BASE / "dockets"
CLUSTERS_DIR = RAW_BASE / "clusters"
OPINIONS_DIR = RAW_BASE / "opinions"

# ── Helpers ────────────────────────────────────────────────────────────────────


def make_client() -> httpx.Client:
    """Create a shared httpx client for the full run."""
    if not TOKEN:
        raise RuntimeError("COURTLISTENER_TOKEN not set in environment")
    return httpx.Client(
        headers={"Authorization": f"Token {TOKEN}"},
        timeout=httpx.Timeout(connect=10, read=60, write=10, pool=10),
        # Keep HTTP behavior deterministic inside the containerized runtime.
        # Manual verification for CourtListener requests was performed with trust_env=False.
        trust_env=False,
    )


def save_json(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + replace to avoid partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def load_json_safe(path: Path) -> dict | None:
    """Read and parse a JSON file. Returns None if file is missing or corrupt."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [warn] Could not read {path}: {e}")
        return None


def already_fetched(path: Path, force: bool) -> bool:
    return path.exists() and not force


def parse_id_from_url(url: str) -> int | None:
    """Parse a numeric ID from the last path segment of a CourtListener URL."""
    try:
        return int(url.rstrip("/").split("/")[-1])
    except (ValueError, IndexError):
        return None


def api_get(
    client: httpx.Client, url: str, params: dict | None = None, sleep: float = 0.5
) -> dict:
    """Make a GET request to the CourtListener API with rate limiting."""
    response = client.get(url, params=params)
    response.raise_for_status()
    time.sleep(sleep)
    return response.json()


# ── Object-level fetchers ──────────────────────────────────────────────────────
#
# Each helper returns (data, outcome) where outcome is one of:
#   "skipped"   — file existed and was readable, no network call made
#   "fetched"   — file did not exist (or --force); fetched from API
#   "refetched" — file existed but was corrupt; refetched from API

FetchStatus: TypeAlias = Literal["skipped", "fetched", "refetched"]
FetchOutcome: TypeAlias = tuple[dict | None, FetchStatus]


def maybe_fetch_docket(
    client: httpx.Client, docket_id: int, force: bool, sleep: float
) -> FetchOutcome:
    """Fetch and save a docket if not already present (or if corrupt)."""
    path = DOCKETS_DIR / f"docket_{docket_id}.json"

    if already_fetched(path, force):
        data = load_json_safe(path)
        if data is not None:
            print(f"  [skip] docket {docket_id}")
            return data, "skipped"
        print(f"  [corrupt] docket {docket_id} — refetching")
        data = api_get(client, f"{BASE_URL}/dockets/{docket_id}/", sleep=sleep)
        save_json(path, data)
        return data, "refetched"

    print(f"  [fetch] docket {docket_id}")
    data = api_get(client, f"{BASE_URL}/dockets/{docket_id}/", sleep=sleep)
    save_json(path, data)
    return data, "fetched"


def maybe_fetch_cluster(
    client: httpx.Client, cluster_id: int, force: bool, sleep: float
) -> FetchOutcome:
    """Fetch and save a cluster if not already present (or if corrupt)."""
    path = CLUSTERS_DIR / f"cluster_{cluster_id}.json"

    if already_fetched(path, force):
        data = load_json_safe(path)
        if data is not None:
            print(f"  [skip] cluster {cluster_id}")
            return data, "skipped"
        print(f"  [corrupt] cluster {cluster_id} — refetching")
        data = api_get(client, f"{BASE_URL}/clusters/{cluster_id}/", sleep=sleep)
        save_json(path, data)
        return data, "refetched"

    print(f"  [fetch] cluster {cluster_id}")
    data = api_get(client, f"{BASE_URL}/clusters/{cluster_id}/", sleep=sleep)
    save_json(path, data)
    return data, "fetched"


def maybe_fetch_opinion(
    client: httpx.Client, opinion_id: int, force: bool, sleep: float
) -> FetchOutcome:
    """Fetch and save an opinion if not already present (or if corrupt)."""
    path = OPINIONS_DIR / f"opinion_{opinion_id}.json"

    if already_fetched(path, force):
        data = load_json_safe(path)
        if data is not None:
            print(f"  [skip] opinion {opinion_id}")
            return data, "skipped"
        print(f"  [corrupt] opinion {opinion_id} — refetching")
        data = api_get(client, f"{BASE_URL}/opinions/{opinion_id}/", sleep=sleep)
        save_json(path, data)
        return data, "refetched"

    print(f"  [fetch] opinion {opinion_id}")
    data = api_get(client, f"{BASE_URL}/opinions/{opinion_id}/", sleep=sleep)
    save_json(path, data)
    return data, "fetched"


# ── Slice fetcher ──────────────────────────────────────────────────────────────


def fetch_scotus_published(
    client: httpx.Client, limit: int, force: bool, sleep: float
) -> None:
    """
    Fetch published SCOTUS opinions via a clusters-first strategy.

    Strategy:
    - Query the clusters endpoint (one join cheaper than opinions endpoint)
    - For each cluster: save cluster, fetch parent docket, fetch each sub-opinion
    - Count limit against opinions, not clusters
    - Stop once the opinion limit is reached
    - No API-side ordering (omitted: inconsistent behavior observed during testing)
    """
    print(f"\nFetching up to {limit} published SCOTUS opinions (clusters-first)...\n")

    params = {
        "docket__court": "scotus",
        "precedential_status": "Published",
        "page_size": 20,
    }

    opinions_processed = 0
    fetched = 0
    skipped = 0
    refetched = 0
    url = f"{BASE_URL}/clusters/"

    while url and opinions_processed < limit:
        print(
            f"Fetching clusters page (opinions processed so far: {opinions_processed})..."
        )
        page = api_get(
            client, url, params=params if "?" not in url else None, sleep=sleep
        )
        results = page.get("results", [])

        if not results:
            break

        for cluster in results:
            if opinions_processed >= limit:
                break

            cluster_id = cluster.get("id")
            if not cluster_id:
                print("  [warn] Cluster missing id — skipping")
                continue

            print(f"\nCluster {cluster_id}:")

            # Fetch and save cluster; use the returned canonical object for traversal
            cluster_detail, _ = maybe_fetch_cluster(client, cluster_id, force, sleep)
            if not cluster_detail:
                print(f"  [warn] Could not retrieve cluster {cluster_id} — skipping")
                continue

            # Fetch parent docket from canonical cluster detail
            docket_id = cluster_detail.get("docket_id")
            if docket_id:
                maybe_fetch_docket(client, docket_id, force, sleep)
            else:
                print(f"  [warn] Cluster {cluster_id} has no docket_id")

            # Fetch each sub-opinion from canonical cluster detail; count against limit
            for opinion_url in cluster_detail.get("sub_opinions", []):
                if opinions_processed >= limit:
                    break

                opinion_id = parse_id_from_url(opinion_url)
                if not opinion_id:
                    print(
                        f"  [warn] Could not parse opinion ID from URL: {opinion_url}"
                    )
                    continue

                _, outcome = maybe_fetch_opinion(client, opinion_id, force, sleep)
                if outcome == "skipped":
                    skipped += 1
                elif outcome == "refetched":
                    refetched += 1
                else:
                    fetched += 1
                opinions_processed += 1

        # Cursor pagination — next URL carries all params
        url = page.get("next")
        params = None

    summary = f"{fetched} fetched, {skipped} skipped"
    if refetched:
        summary += f", {refetched} refetched (corrupt)"
    print(f"\nDone. Processed {opinions_processed} opinions ({summary}).")


# ── Landmark case fetcher ──────────────────────────────────────────────────────

# Curated list of landmark SCOTUS cluster IDs for Pass 2.
# These are CourtListener cluster IDs for well-known cases.
# Expand this list as needed.
LANDMARK_CLUSTER_IDS: list[int] = [
    # Add landmark cluster IDs here for Pass 2
    # e.g. 2812209 = Obergefell v. Hodges
]


def fetch_landmarks(client: httpx.Client, force: bool, sleep: float) -> None:
    """Fetch curated landmark cases by cluster ID."""
    if not LANDMARK_CLUSTER_IDS:
        print("No landmark cluster IDs configured. Add them to LANDMARK_CLUSTER_IDS.")
        return

    print(f"\nFetching {len(LANDMARK_CLUSTER_IDS)} landmark clusters...\n")

    for cluster_id in LANDMARK_CLUSTER_IDS:
        print(f"\nCluster {cluster_id}:")
        cluster, _ = maybe_fetch_cluster(client, cluster_id, force, sleep)

        if not cluster:
            continue

        # Fetch parent docket
        docket_id = cluster.get("docket_id")
        if docket_id:
            maybe_fetch_docket(client, docket_id, force, sleep)

        # Fetch all sub-opinions
        for opinion_url in cluster.get("sub_opinions", []):
            opinion_id = parse_id_from_url(opinion_url)
            if opinion_id:
                maybe_fetch_opinion(client, opinion_id, force, sleep)
            else:
                print(f"  [warn] Could not parse opinion ID from URL: {opinion_url}")

    print("\nDone fetching landmark cases.")


# ── CLI ────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch raw CourtListener data for the legal casebase."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max number of opinions to fetch in Pass 1 (default: 100)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing raw files (default: skip existing)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Delay between API requests in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--landmarks",
        action="store_true",
        help="Fetch curated landmark cases (Pass 2)",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        parser.error("--limit must be greater than 0")
    if args.sleep < 0:
        parser.error("--sleep must be >= 0")

    return args


def main() -> None:
    args = parse_args()

    with make_client() as client:
        if args.landmarks:
            fetch_landmarks(client, force=args.force, sleep=args.sleep)
        else:
            fetch_scotus_published(
                client, limit=args.limit, force=args.force, sleep=args.sleep
            )


if __name__ == "__main__":
    main()
