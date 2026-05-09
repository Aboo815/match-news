#!/usr/bin/env python3
"""Generate FootballAnt Match News RSS feed from static pages."""
from __future__ import annotations

import argparse
import email.utils
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
BASE = "https://www.footballant.com/match-news/"
FEED_URL = BASE + "feed.xml"
SITE_TITLE = "FootballAnt Match Signals"
SITE_DESC = "FootballAnt lineup clarity, fan mood, chaos watch and pre-match football intelligence."
ROBOTS_RE = re.compile(r'<link rel="alternate" type="application/rss\+xml" title="FootballAnt Match Signals" href="feed.xml"\s*/?>')


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def title_from(text: str) -> str:
    return clean((re.search(r"<title>(.*?)</title>", text, re.S) or [None, "FootballAnt Match News"])[1]).replace(" | FootballAnt", "")


def desc_from(text: str) -> str:
    m = re.search(r'<meta name="description" content="([^"]+)"', text, re.S)
    if m:
        return clean(m.group(1))
    m = re.search(r'<p class="answer">(.*?)</p>', text, re.S)
    return clean(m.group(1)) if m else SITE_DESC


def pubdate(path: Path) -> str:
    dt = datetime.fromtimestamp(path.stat().st_mtime, TZ)
    return email.utils.format_datetime(dt)


def url_for(root: Path, path: Path) -> str:
    rel = path.parent.relative_to(root).as_posix()
    if rel == ".":
        return BASE
    return BASE + rel.strip("/") + "/"


def collect_items(root: Path, limit: int = 60) -> list[dict]:
    candidates = []
    fixed = [
        root / "index.html",
        root / "latest-football-lineup-predictions" / "index.html",
        root / "today-football-lineups" / "index.html",
        root / "tomorrow-football-lineups" / "index.html",
        root / "todays-most-stable-matches" / "index.html",
        root / "fan-mood-index" / "index.html",
        root / "match-fortune-today" / "index.html",
    ]
    candidates.extend([p for p in fixed if p.exists()])
    match_pages = list((root / "matches").glob("*/index.html")) if (root / "matches").exists() else []
    candidates.extend(sorted(match_pages, key=lambda p: p.stat().st_mtime, reverse=True)[:limit])
    seen = set()
    items = []
    for p in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        u = url_for(root, p)
        if u in seen:
            continue
        seen.add(u)
        text = p.read_text(encoding="utf-8", errors="ignore")
        items.append({"title": title_from(text), "url": u, "desc": desc_from(text), "pubDate": pubdate(p)})
        if len(items) >= limit:
            break
    return items


def write_feed(root: Path, items: list[dict]) -> None:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for tag, val in [
        ("title", SITE_TITLE),
        ("link", BASE),
        ("description", SITE_DESC),
        ("language", "en"),
        ("lastBuildDate", email.utils.format_datetime(datetime.now(TZ))),
        ("ttl", "60"),
    ]:
        ET.SubElement(channel, tag).text = val
    for item in items:
        node = ET.SubElement(channel, "item")
        ET.SubElement(node, "title").text = item["title"]
        ET.SubElement(node, "link").text = item["url"]
        ET.SubElement(node, "guid", isPermaLink="true").text = item["url"]
        ET.SubElement(node, "description").text = item["desc"]
        ET.SubElement(node, "pubDate").text = item["pubDate"]
    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(root / "feed.xml", encoding="utf-8", xml_declaration=True)


def patch_home(root: Path) -> bool:
    path = root / "index.html"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    if 'type="application/rss+xml"' in text and 'feed.xml' in text:
        return False
    link = '  <link rel="alternate" type="application/rss+xml" title="FootballAnt Match Signals" href="feed.xml" />\n'
    new = text.replace("</head>", link + "</head>", 1)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def update_sitemap(root: Path) -> bool:
    path = root / "sitemap.xml"
    if not path.exists():
        return False
    xml = path.read_text(encoding="utf-8", errors="ignore")
    loc = BASE + "feed.xml"
    today = datetime.now(TZ).date().isoformat()
    if f"<loc>{loc}</loc>" in xml:
        new = re.sub(rf"(<loc>{re.escape(loc)}</loc>\s*<lastmod>)[^<]+", rf"\g<1>{today}", xml)
    else:
        block = f'''  <url>\n    <loc>{loc}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>hourly</changefreq>\n    <priority>0.6</priority>\n  </url>\n'''
        new = xml.replace("</urlset>", block + "</urlset>")
    if new != xml:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def optimize(root: Path) -> dict:
    items = collect_items(root)
    write_feed(root, items)
    return {"root": str(root), "items": len(items), "home_patched": patch_home(root), "sitemap_patched": update_sitemap(root)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", required=True)
    args = ap.parse_args()
    results = [optimize(Path(r)) for r in args.root]
    print({"status": "ok", "results": results})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
