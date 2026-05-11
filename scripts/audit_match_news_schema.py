#!/usr/bin/env python3
"""Audit generated match-news HTML for SEO/schema regressions.

This is intentionally dependency-free so heartbeat/cron checks can run it quickly.
It focuses on issues that have already caused GSC or indexability problems:
- Cloudflare/indexability metadata on HTML pages (checked locally by markup presence)
- SportsEvent missing required Event fields such as location/description
- internal workflow wording leaking to public pages
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

INTERNAL_PHRASE_RE = re.compile(
    r"draft|pre-publish|not publish-ready|static search-entry|users and search engines|fastest article clicks",
    re.I,
)
JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def load_jsonld_graphs(html: str) -> list[dict[str, Any]]:
    graphs: list[dict[str, Any]] = []
    for match in JSONLD_RE.finditer(html):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            graph = payload.get("@graph")
            if isinstance(graph, list):
                graphs.extend(node for node in graph if isinstance(node, dict))
            else:
                graphs.append(payload)
    return graphs


def audit_file(path: Path, root: Path) -> list[str]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    rel = str(path.relative_to(root))
    issues: list[str] = []

    if INTERNAL_PHRASE_RE.search(html):
        issues.append(f"{rel}: internal_phrase_leak")

    is_match_page = rel.startswith("matches/") and rel.endswith("/index.html")
    is_entry_page = rel in {
        "index.html",
        "latest-football-lineup-predictions/index.html",
        "premier-league-lineup-predictions/index.html",
        "champions-league-lineup-predictions/index.html",
        "la-liga-lineup-predictions/index.html",
        "serie-a-lineup-predictions/index.html",
        "bundesliga-lineup-predictions/index.html",
    }

    if is_match_page or is_entry_page:
        if "max-snippet:-1" not in html or "max-image-preview:large" not in html:
            issues.append(f"{rel}: missing_robots_preview_meta")
        if 'rel="canonical"' not in html:
            issues.append(f"{rel}: missing_canonical")
        if 'property="og:image"' not in html:
            issues.append(f"{rel}: missing_og_image")
        if 'application/ld+json' not in html:
            issues.append(f"{rel}: missing_jsonld")

    graphs = load_jsonld_graphs(html)
    if is_match_page:
        news_articles = [node for node in graphs if node.get("@type") in {"NewsArticle", "Article"}]
        if not any(node.get("image") for node in news_articles):
            issues.append(f"{rel}: missing_newsarticle_image")
        if not any(node.get("@type") == "BreadcrumbList" for node in graphs):
            issues.append(f"{rel}: missing_breadcrumb_schema")
        if not any(node.get("@type") == "ImageObject" for node in graphs):
            issues.append(f"{rel}: missing_imageobject_schema")

    sports_events = [node for node in graphs if node.get("@type") == "SportsEvent"]
    for index, event in enumerate(sports_events, start=1):
        prefix = f"{rel}: SportsEvent[{index}]"
        if not event.get("name"):
            issues.append(f"{prefix} missing_name")
        if not event.get("startDate"):
            issues.append(f"{prefix} missing_startDate")
        if not event.get("description"):
            issues.append(f"{prefix} missing_description")
        location = event.get("location")
        if not isinstance(location, dict) or not location.get("name"):
            issues.append(f"{prefix} missing_location_name")
        competitors = event.get("competitor")
        if not isinstance(competitors, list) or len(competitors) < 2:
            issues.append(f"{prefix} missing_competitors")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit match-news generated HTML schema/SEO markup.")
    parser.add_argument("root", nargs="?", default=".", help="publish root, default current directory")
    parser.add_argument("--limit", type=int, default=50, help="issue print limit")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    html_files = sorted(root.glob("**/*.html"))
    issues: list[str] = []
    event_pages = 0
    for path in html_files:
        html = path.read_text(encoding="utf-8", errors="ignore")
        if "SportsEvent" in html:
            event_pages += 1
        issues.extend(audit_file(path, root))

    summary = {
        "root": str(root),
        "html_files": len(html_files),
        "sportsevent_pages": event_pages,
        "issue_count": len(issues),
    }
    print(json.dumps(summary, ensure_ascii=False))
    for issue in issues[: args.limit]:
        print(issue)
    if len(issues) > args.limit:
        print(f"... {len(issues) - args.limit} more issues")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
