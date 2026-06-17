#!/usr/bin/env python3
"""One-time provisioning of the Agent Search premium-publisher data store.

This script creates a website data store with `basic` indexing (so we can
include third-party domains we don't own) and seeds it with the premium
financial publishers we want Mode A deep research to consult.

Run once, manually, by a project admin. Stores the resulting data store ID
in stdout — paste into `.env` as `SHINKAI_AGENT_SEARCH_DATA_STORE_ID`.

Prerequisites:
  - Discovery Engine API enabled on the project
  - SA running this script has `roles/discoveryengine.admin`
  - ADC configured (`gcloud auth application-default login`)

Usage:
  python scripts/provision-premium-data-store.py \\
      --project shinkai-research \\
      --display-name "Premium financial publishers" \\
      [--data-store-id premium-news] \\
      [--location global] \\
      [--dry-run]

The default seed list covers the publishers shinkai treats as secondary-or-better
sources. Edit `PREMIUM_PUBLISHERS` to add / remove. Up to 50 patterns per data
store; advanced indexing (and its domain-verification requirement) is NEVER
turned on by this script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib.parse import urlparse

import httpx

# Premium financial publishers — match what we treat as secondary-tier in
# research/models.py::_SECONDARY_PUBLISHER_HINTS, plus a few must-haves.
# Each pattern is a glob: see https://cloud.google.com/agent-search/...
PREMIUM_PUBLISHERS: list[str] = [
    # Major financial press
    "wsj.com/*",
    "bloomberg.com/*",
    "reuters.com/*",
    "ft.com/*",
    "cnbc.com/*",
    "barrons.com/*",
    "marketwatch.com/*",
    "nytimes.com/*",
    "economist.com/*",
    # Asia
    "asia.nikkei.com/*",
    "scmp.com/*",
    "caixinglobal.com/*",
    # Specialty trade
    "semianalysis.com/*",
    "semiengineering.com/*",
    "digitimes.com/*",
    "trendforce.com/*",
    # Primary
    "sec.gov/Archives/edgar/data/*",
]

EXCLUDE_PATTERNS: list[str] = [
    # SEC paths that don't carry document content
    "sec.gov/cgi-bin/*",
]


def _access_token() -> str:
    """Resolve ADC and return a cloud-platform-scoped access token."""
    try:
        import google.auth
        import google.auth.transport.requests
    except ImportError:
        sys.exit("google-auth required: pip install google-auth")
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _create_data_store(
    token: str, project: str, location: str, data_store_id: str, display_name: str
) -> dict[str, Any]:
    url = (
        f"https://discoveryengine.googleapis.com/v1/"
        f"projects/{project}/locations/{location}/collections/default_collection/dataStores"
        f"?dataStoreId={data_store_id}"
    )
    body = {
        "displayName": display_name,
        "industryVertical": "GENERIC",
        "contentConfig": "PUBLIC_WEBSITE",
        "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
    }
    resp = httpx.post(url, json=body, headers=_headers(token), timeout=60.0)
    if resp.status_code == 409:
        print(f"  data store {data_store_id} already exists, skipping create", file=sys.stderr)
        return {}
    resp.raise_for_status()
    return resp.json()


def _add_target_site(
    token: str,
    project: str,
    location: str,
    data_store_id: str,
    pattern: str,
    *,
    exclude: bool,
) -> dict[str, Any]:
    url = (
        f"https://discoveryengine.googleapis.com/v1/"
        f"projects/{project}/locations/{location}/collections/default_collection/"
        f"dataStores/{data_store_id}/siteSearchEngine/targetSites"
    )
    body = {
        "providedUriPattern": pattern,
        "type": "EXCLUDE" if exclude else "INCLUDE",
        # exactMatch=False allows wildcards and subpaths.
        "exactMatch": False,
    }
    resp = httpx.post(url, json=body, headers=_headers(token), timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="GCP project id")
    parser.add_argument(
        "--data-store-id",
        default="premium-news",
        help="Lowercase a-z0-9- only, max 63 chars",
    )
    parser.add_argument(
        "--location",
        default="global",
        help="Almost always 'global' for website data stores",
    )
    parser.add_argument(
        "--display-name",
        default="Premium financial publishers",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without calling the API",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN — no API calls will be made")
        print(f"project       : {args.project}")
        print(f"location      : {args.location}")
        print(f"data store id : {args.data_store_id}")
        print(f"display name  : {args.display_name}")
        print()
        print("INCLUDE patterns:")
        for p in PREMIUM_PUBLISHERS:
            print(f"  + {p}")
        print()
        print("EXCLUDE patterns:")
        for p in EXCLUDE_PATTERNS:
            print(f"  - {p}")
        return 0

    print(f"Provisioning Agent Search data store '{args.data_store_id}' in {args.project}/{args.location}...")
    token = _access_token()
    print("  ADC token acquired")

    created = _create_data_store(
        token, args.project, args.location, args.data_store_id, args.display_name
    )
    if created:
        print(f"  data store created: {created.get('name', '?')}")

    # Target sites need a brief delay after data store creation for the
    # SiteSearchEngine to materialize. 5s is conservative.
    print("  waiting 5s for site search engine to initialize...")
    time.sleep(5)

    for pat in PREMIUM_PUBLISHERS:
        result = _add_target_site(
            token, args.project, args.location, args.data_store_id, pat, exclude=False
        )
        print(f"  + INCLUDE {pat}  ({result.get('name', '?').split('/')[-1]})")

    for pat in EXCLUDE_PATTERNS:
        result = _add_target_site(
            token, args.project, args.location, args.data_store_id, pat, exclude=True
        )
        print(f"  - EXCLUDE {pat}  ({result.get('name', '?').split('/')[-1]})")

    print()
    print("Done. Add to your .env file:")
    print()
    print(f"  SHINKAI_AGENT_SEARCH_PROJECT={args.project}")
    print(f"  SHINKAI_AGENT_SEARCH_DATA_STORE_ID={args.data_store_id}")
    print(f"  SHINKAI_AGENT_SEARCH_LOCATION={args.location}")
    print()
    print("Indexing takes 1-4 hours before queries return results. Check the")
    print("Agent Search console under 'Activity' for indexing status.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
