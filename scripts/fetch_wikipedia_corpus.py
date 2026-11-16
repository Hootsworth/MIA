#!/usr/bin/env python3
# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Collect a revision-pinned English Wikipedia reference sample via its public API.

Raw page text and corpus manifests are written under storage/, never committed.
The script uses a descriptive User-Agent and pauses between requests.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://en.wikipedia.org/w/api.php"
LICENSE = "CC BY-SA 4.0 (Wikipedia text; check individual article notices)"
USER_AGENT = "MIA research toolkit corpus collector/0.4 (https://github.com/Hootsworth/MIA)"


def get_json(parameters: dict) -> dict:
    url = f"{API}?{urlencode(parameters)}"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(8):
        try:
            with urlopen(request, timeout=45) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in {429, 503} or attempt == 7:
                raise
            wait = error.headers.get("Retry-After")
            delay = float(wait) if wait and wait.isdigit() else min(120, 2 ** (attempt + 2))
            print(f"Wikipedia API returned HTTP {error.code}; retrying after {delay:.0f}s", file=sys.stderr)
            time.sleep(delay)
    raise RuntimeError("Wikipedia API retry loop ended unexpectedly")


def collect_page_ids(count: int, delay: float, exclude: set[int] | None = None) -> list[int]:
    selected: dict[int, str] = {}
    excluded = exclude or set()
    while len(selected) < count:
        page = get_json({"action": "query", "list": "random", "rnnamespace": 0,
                         "rnlimit": min(50, max(20, (count - len(selected)) * 2)), "format": "json"})
        for item in page["query"]["random"]:
            page_id = int(item["id"])
            if page_id not in excluded:
                selected[page_id] = item["title"]
        if len(selected) < count:
            time.sleep(delay)
    return list(selected)[:count]


def fetch_pages(page_ids: list[int], delay: float, on_page=None):
    output = []
    for offset in range(0, len(page_ids), 20):
        batch = page_ids[offset : offset + 20]
        page = get_json({"action": "query", "pageids": "|".join(map(str, batch)),
                         "prop": "extracts|info|revisions", "explaintext": 1,
                         "exintro": 1, "exlimit": 20, "inprop": "url",
                         "rvprop": "ids", "format": "json"})
        for entry in page.get("query", {}).get("pages", {}).values():
            revisions = entry.get("revisions", [])
            text = entry.get("extract", "").strip()
            if entry.get("missing") is not None or not text or not revisions:
                continue
            article = {
                "page_id": int(entry["pageid"]),
                "title": entry["title"],
                "source_url": entry.get("fullurl", ""),
                "revision_id": int(revisions[0]["revid"]),
                "text": text,
            }
            output.append(article)
            if on_page:
                on_page(article)
        print(f"Fetched page batch {offset // 20 + 1}/{(len(page_ids) + 19) // 20}", flush=True)
        if offset + 20 < len(page_ids):
            time.sleep(delay)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=Path("storage/reference-corpus/wikipedia-en"))
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between API calls (default: 1)")
    parser.add_argument("--resume", action="store_true", help="continue a prior partial collection in this output directory")
    args = parser.parse_args()
    if args.count < 1 or args.delay < 0:
        parser.error("--count must be positive and --delay cannot be negative")
    if args.output.exists() and any(args.output.iterdir()) and not args.resume:
        parser.error("--output must be a new or empty directory; choose a new collection path to preserve prior files")

    args.output.mkdir(parents=True, exist_ok=True)
    existing_ids = set()
    if args.resume:
        for path in args.output.glob("*.txt"):
            try:
                existing_ids.add(int(path.stem))
            except ValueError:
                continue
    pages_by_id = {}

    def save_page(page):
        pages_by_id[page["page_id"]] = page
        (args.output / f"{page['page_id']}.txt").write_text(page["text"] + "\n", encoding="utf-8")

    if existing_ids:
        fetch_pages(sorted(existing_ids), args.delay, save_page)
    attempts = 0
    while len(pages_by_id) < args.count and attempts < 5:
        page_ids = collect_page_ids(args.count - len(pages_by_id), args.delay, set(pages_by_id))
        fetch_pages(page_ids, args.delay, save_page)
        print(f"Collected {len(pages_by_id)}/{args.count} pages", flush=True)
        attempts += 1
    pages = list(pages_by_id.values())[: args.count]
    if len(pages) < args.count:
        print(f"mia-corpus: requested {args.count} pages but retrieved {len(pages)} after five attempts", file=sys.stderr)
    documents = []
    for page in pages:
        relative_path = f"{page['page_id']}.txt"
        encoded = (page["text"] + "\n").encode("utf-8")
        (args.output / relative_path).write_bytes(encoded)
        permanent_url = f"{page['source_url'].split('/wiki/')[0]}/w/index.php?oldid={page['revision_id']}"
        documents.append({
            "path": relative_path,
            "title": page["title"],
            "page_id": page["page_id"],
            "revision_id": page["revision_id"],
            "source_url": permanent_url,
            "license": LICENSE,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "word_count": len(page["text"].split()),
        })
    manifest = {
        "dataset": "English Wikipedia random namespace-0 article introductions",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source_api": API,
        "source_license": LICENSE,
        "attribution": "Each record links to the exact page revision; see the Wikipedia article history for contributors.",
        "modifications": "Plain-text article introductions returned by the MediaWiki API; no editorial rewriting.",
        "documents": documents,
    }
    (args.output / "corpus-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"requested": args.count, "collected": len(documents), "directory": str(args.output),
                      "manifest": str(args.output / "corpus-manifest.json")}, indent=2))
    return 0 if len(documents) == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
