# Engineering Investigation Report: CourtListener Fetch Strategy Timeouts in `scripts/fetch.py`

**Project:** Legal Casebase
**Phase:** Phase 2 — Ingestion + Indexing
**Date:** 2026-04-13
**Author:** Shobhit Gupta
**Status:** Resolved / Strategy Updated

## 1. Summary

While implementing the raw acquisition script `scripts/fetch.py`, we encountered repeated timeouts during the very first API page fetch against CourtListener.

The original strategy queried the **`opinions`** endpoint first using cross-table filters to obtain recent published SCOTUS opinions, then fetched parent clusters and dockets for each opinion.

This approach proved operationally unreliable. Manual testing showed that the original query shape was too expensive for bulk fetching. Further investigation revealed that even an alternative **`clusters`** query became expensive when combined with server-side ordering by `date_filed`.

The fetch strategy was revised based on manual verification. The new strategy is:

* query **`clusters`** first
* use only cheap filters
* avoid API-side ordering
* traverse:

  * cluster
  * parent docket
  * sub-opinions

This report explains:

* what failed
* how we debugged it
* what we learned
* why the new strategy was chosen
* what was manually verified before rewriting the script

---

## 2. Original Goal of `fetch.py`

`scripts/fetch.py` is responsible for **raw acquisition only**.

Its intended responsibilities are:

* call the CourtListener API
* fetch raw payloads for the target corpus slice
* save JSON snapshots under `storage/raw/courtlistener/`
* support reruns safely

It is **not** responsible for:

* normalization
* SQLite writes
* chunking
* embeddings
* FAISS
* application-serving behavior

---

## 3. Original Fetch Strategy

The original Pass 1 fetch strategy was:

1. Query the **`opinions`** endpoint using filters intended to represent recent published SCOTUS opinions.
2. For each opinion returned:

   * save the opinion JSON
   * fetch its parent cluster
   * fetch the parent docket from that cluster

The first-page query was effectively:

```text
GET /api/rest/v4/opinions/
    ?cluster__docket__court=scotus
    &cluster__precedential_status=Published
    &order_by=-cluster__date_filed
    &page_size=20
```

This was chosen because it appeared to map closely to the desired corpus slice.

---

## 4. Problem Encountered

Every real run of `fetch.py` failed at the very first page fetch with a timeout.

Example failure pattern:

* script started
* first opinions page requested
* request blocked until read timeout
* script aborted before any useful data acquisition

This made the original fetch strategy operationally unusable.

---

## 5. Symptoms

Observed symptoms included:

* `httpx.ReadTimeout`
* timeouts at the first opinions page request
* repeated failure even after increasing timeouts
* no end-to-end data acquisition progress from the original script path

The issue appeared early enough that no meaningful ingestion progress was being made.

---

## 6. Initial Hypotheses Considered

During debugging, several explanations were considered:

1. CourtListener server slowness
2. bad query shape
3. container networking problem
4. proxy or environment-variable interference inside the container
5. HTTP client behavior / timeout configuration
6. specific endpoint cost versus general connectivity issue

These hypotheses were investigated step by step.

---

## 7. Debugging Steps Taken

### 7.1 Increased timeout

The original flat timeout was increased, and later explicit read timeouts were used.

Result:

* timeouts still occurred
* increasing timeout did not meaningfully fix the problem
* this suggested the problem was strategic, not just timeout tuning

### 7.2 Verified the script file was actually updated in the container

The active script inside the container was checked to confirm timeout edits were actually present.

Result:

* confirmed that the intended code changes were reaching the runtime environment

### 7.3 Host-side manual request for the original opinions query

The original opinions-first query was run manually from the host to test whether CourtListener itself was slow for that query shape.

Observed result:

* the request did return
* but it took a very long time (on the order of ~100 seconds for one page of 20 results)

Interpretation:

* the query shape itself was expensive
* this was not just a Python or container issue

### 7.4 Container-side direct endpoint checks

Simple endpoint checks were run from inside the container using Python and `httpx`.

These tests included:

* simple court detail endpoint
* clusters query without ordering
* clusters query with ordering
* opinions deep-filter query

This helped distinguish:

* general connectivity
* endpoint-specific performance
* query-shape cost

### 7.5 Proxy / environment inspection inside the container

Proxy- and certificate-related environment variables were checked inside the container.

Result:

* no suspicious proxy or cert overrides were present

Interpretation:

* proxy-env poisoning was not the cause

### 7.6 `trust_env=False` tests

Container-side requests were executed using `httpx.Client(..., trust_env=False)`.

Result:

* simple CourtListener requests worked
* clusters query without expensive ordering also worked

Interpretation:

* general network and TLS connectivity from the container was fine
* the expensive query shape remained the main issue

### 7.7 Alternative query-shape investigation

The `clusters` endpoint was tested directly.

Two patterns were compared:

1. `clusters` query **without** `order_by`
2. `clusters` query **with** `order_by=-date_filed`

Observed pattern:

* unordered `clusters` requests were reasonably fast
* ordered requests could become very slow or timeout
* this indicated that API-side ordering was a major contributor to the problem

---

## 8. Root Cause

The original strategy relied on an expensive CourtListener query shape.

There were two related problems:

### 8.1 Opinions-first deep cross-table query was too expensive

The original fetch path queried the `opinions` endpoint using cross-table filters such as:

* `cluster__docket__court=scotus`
* `cluster__precedential_status=Published`

This forced the server into a deeper, more expensive query path.

### 8.2 API-side ordering made things worse

Adding:

* `order_by=-cluster__date_filed`
  or, on clusters,
* `order_by=-date_filed`

made the query significantly slower and less reliable.

### Root-cause conclusion

The timeout problem was fundamentally a **fetch-strategy / query-shape problem**, not primarily:

* an auth issue
* a Docker issue
* a proxy issue
* or a local Python bug

---

## 9. Key Technical Findings

The investigation established the following:

1. **General container connectivity was fine**

   * simple CourtListener endpoints worked from inside the container

2. **Proxy environment interference was not the issue**

   * no relevant proxy-related environment variables were found

3. **The expensive part was the query shape**

   * especially deep opinions filtering and API-side ordering

4. **`clusters` without expensive ordering was viable**

   * this provided a better starting point for raw acquisition

5. **Cluster traversal gives the full hierarchy needed**

   * cluster detail exposes `docket_id`
   * cluster detail exposes `sub_opinions`
   * therefore cluster → docket + sub-opinions is enough for raw acquisition

---

## 10. Manual Verification Performed Before Rewriting

Before changing the fetch strategy, the candidate replacement path was manually verified.

### 10.1 Host check: unordered `clusters` query

The unordered `clusters` query was run on the host.

Result:

* response was fast enough to be viable

### 10.2 Container check: unordered `clusters` query

The same unordered `clusters` query was tested inside the container.

Result:

* response was successful and reasonably fast

### 10.3 Cluster list response inspection

A cluster from the list response was inspected.

Verified fields included:

* `id`
* `docket_id`
* `date_filed`
* `case_name`
* `sub_opinions`

Interpretation:

* the list response already provided enough information to support clusters-first traversal

### 10.4 Cluster detail fetch by ID

A cluster was fetched directly by ID.

Result:

* fast and reliable

### 10.5 Parent docket fetch by ID

The parent docket referenced by the cluster was fetched by `docket_id`.

Result:

* fast and reliable

### 10.6 Sub-opinion fetch by ID

A sub-opinion referenced by the cluster was fetched by ID.

Result:

* fast and reliable

### 10.7 Cursor pagination check

The `next` cursor URL was followed manually.

Result:

* cursor pagination worked
* latency was somewhat variable, but viable overall

### Manual-verification conclusion

The new traversal model was validated end to end:

* clusters list
* cluster detail
* parent docket
* sub-opinions
* cursor pagination

This gave sufficient confidence to rewrite the script.

---

## 11. Final Strategy Chosen

The original opinions-first strategy was replaced with a **clusters-first** strategy.

### New approach

1. Query the **`clusters`** endpoint first
2. Apply only cheap filters:

   * `docket__court=scotus`
   * `precedential_status=Published`
3. Avoid expensive API-side ordering
4. Use cursor pagination
5. For each cluster:

   * save cluster JSON
   * fetch/save parent docket via `docket_id`
   * fetch/save each sub-opinion via `sub_opinions`

### Why this was chosen

This strategy is better because it is:

* closer to the source hierarchy
* operationally viable
* validated manually before implementation
* simpler to reason about than continuing to fight the expensive opinions-first query

---

## 12. Changes Made to the Script Along the Way

During the debugging and hardening process, several worthwhile improvements were made to `fetch.py`, even though they were not the root cause of the timeout:

* shared `httpx.Client()` for the whole run
* explicit client lifecycle via context manager
* atomic JSON writes using temp file + replace
* corrupt-file detection with refetch fallback
* structured helper outcomes (`skipped`, `fetched`, `refetched`)
* CLI validation for `--limit` and `--sleep`
* improved operational reporting

These changes improved correctness, rerun safety, and technical quality, but they did not solve the original timeout problem by themselves.

---

## 13. Lessons Learned

### 13.1 Query-shape verification should happen earlier

We spent time polishing implementation details before fully validating the fetch strategy at runtime.

Better approach:

* manually test the exact API query shape first
* then write the script around a proven query plan

### 13.2 Static review is not enough

Code review helped improve structure and robustness, but the main failure was only revealed through runtime behavior.

### 13.3 API semantics and API performance are different things

A query can be logically correct and still be operationally wrong for bulk fetching.

### 13.4 Manual verification before rewrite is worth it

The manual checks gave confidence that the replacement strategy would actually work before another round of coding.

---

## 14. Outcome

The fetch strategy was successfully redefined from:

* **opinions-first with deep filters and expensive ordering**

to:

* **clusters-first without expensive API-side ordering**

This resolved the main design issue behind the repeated timeouts and provided a viable path forward for Phase 2 raw acquisition.

---

## 15. Designated Space for Pre-Investigation `fetch.py`

Paste the final accepted version of `scripts/fetch.py` below.

```python
# ============================================
# PRE-INVESTIGATION scripts/fetch.py
# ============================================

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
        timeout=30,
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


def api_get(client: httpx.Client, url: str, params: dict | None = None, sleep: float = 0.5) -> dict:
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


def maybe_fetch_docket(client: httpx.Client, docket_id: int, force: bool, sleep: float) -> FetchOutcome:
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


def maybe_fetch_cluster(client: httpx.Client, cluster_id: int, force: bool, sleep: float) -> FetchOutcome:
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


def maybe_fetch_opinion(client: httpx.Client, opinion_id: int, force: bool, sleep: float) -> FetchOutcome:
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

def fetch_scotus_published(client: httpx.Client, limit: int, force: bool, sleep: float) -> None:
    """
    Fetch recent published SCOTUS opinions and their parent clusters and dockets.

    Strategy:
    - Query opinions endpoint filtered to published SCOTUS clusters
    - For each opinion, fetch its parent cluster and parent docket
    - Apply skip logic independently at each object level
    """
    print(f"\nFetching up to {limit} published SCOTUS opinions...\n")

    params = {
        "cluster__docket__court": "scotus",
        "cluster__precedential_status": "Published",
        "order_by": "-cluster__date_filed",
        "page_size": min(limit, 20),  # CourtListener max page size is 20
    }

    processed = 0
    fetched = 0
    skipped = 0
    refetched = 0
    url = f"{BASE_URL}/opinions/"

    while url and processed < limit:
        print(f"Fetching opinions page (processed so far: {processed})...")
        page = api_get(client, url, params=params if "?" not in url else None, sleep=sleep)
        results = page.get("results", [])

        if not results:
            break

        for opinion in results:
            if processed >= limit:
                break

            opinion_id = opinion["id"]

            # Resolve cluster_id from field or fallback to parsing the URL
            cluster_id = opinion.get("cluster_id")
            if not cluster_id:
                cluster_url = opinion.get("cluster", "")
                cluster_id = parse_id_from_url(cluster_url) if cluster_url else None

            print(f"\nOpinion {opinion_id}:")

            # Fetch opinion and record outcome
            _, opinion_outcome = maybe_fetch_opinion(client, opinion_id, force, sleep)
            if opinion_outcome == "skipped":
                skipped += 1
            elif opinion_outcome == "refetched":
                refetched += 1
            else:
                fetched += 1

            # Fetch parent cluster
            if cluster_id:
                cluster, _ = maybe_fetch_cluster(client, cluster_id, force, sleep)

                # Fetch parent docket from cluster
                if cluster:
                    docket_id = cluster.get("docket_id")
                    if docket_id:
                        maybe_fetch_docket(client, docket_id, force, sleep)
            else:
                print(f"  [warn] Could not resolve cluster_id for opinion {opinion_id}")

            processed += 1

        # Pagination — use next URL directly, clear params
        url = page.get("next")
        params = None

    summary = f"{fetched} fetched, {skipped} skipped"
    if refetched:
        summary += f", {refetched} refetched (corrupt)"
    print(f"\nDone. Processed {processed} opinions ({summary}).")


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
            fetch_scotus_published(client, limit=args.limit, force=args.force, sleep=args.sleep)


if __name__ == "__main__":
    main()


# ============================================
```

---

## 16. Designated Space for Final `fetch.py`

Paste the final accepted version of `scripts/fetch.py` below.

```python
# ============================================
# FINAL ACCEPTED scripts/fetch.py
# ============================================

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


# ============================================
```

---

