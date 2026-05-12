#!/usr/bin/env python3
"""Calibrate FootballAnt match-news date hubs to the current Asia/Shanghai date.

This prevents /today-football-lineups/ and /tomorrow-football-lineups/ from
serving stale static dates after homepage/latest publishes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import html
import json
import re

TZ = timezone(timedelta(hours=8))
BASE_URL = "https://www.footballant.com/match-news/"
IMAGE_URL = BASE_URL + "assets/footballant-match-news-preview.png"
ROBOTS = "index,follow,max-snippet:-1,max-image-preview:large,max-video-preview:-1"


def parse_date(value: str):
    value = value.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value).replace("\n", " ").strip()


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def page_records(root: Path) -> list[dict]:
    records = []
    for path in sorted((root / "matches").glob("*/index.html")):
        text = read_text(path)
        title = strip_tags(re.search(r"<title>(.*?)</title>", text, re.S).group(1)) if re.search(r"<title>(.*?)</title>", text, re.S) else ""
        if not title:
            continue
        date_match = re.search(r"\(([^()]+\d{4})\)", title)
        date = parse_date(date_match.group(1)) if date_match else None
        if not date:
            continue
        league = "football"
        league_match = re.search(r"<li><strong>Competition:</strong>\s*([^<]+)</li>", text)
        if league_match:
            league = html.unescape(league_match.group(1)).strip() or league
        slug = path.parent.name
        records.append({"slug": slug, "title": html.unescape(title), "league": league, "date": date})
    records.sort(key=lambda item: (item["date"], item["title"], item["slug"]))
    return records


def item_list(entries: list[dict], prefix: str = "../matches/") -> str:
    rows = []
    for pos, entry in enumerate(entries, start=1):
        rows.append(
            "".join([
                '<li itemprop="itemListElement" itemscope itemtype="https://schema.org/ListItem">\n',
                f'  <a itemprop="item" href="{prefix}{esc(entry["slug"])}/"><span itemprop="name">{esc(entry["title"])}</span></a>\n',
                f'  <p>{esc(entry["league"])} lineup prediction, team news and score prediction.</p>\n',
                f'  <meta itemprop="position" content="{pos}" />\n',
                '</li>',
            ])
        )
    return "\n".join(rows)


def hub_json_ld(kind: str, date_text: str, entries: list[dict], modified: datetime) -> str:
    name = f"{kind.title()} football lineups and predicted XI | FootballAnt"
    url = f"{BASE_URL}{kind}-football-lineups/"
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "url": url,
                "name": name,
                "description": f"Find {kind} football lineups, predicted XIs, team news and score predictions before kickoff on FootballAnt.",
                "isPartOf": {"@id": "https://www.footballant.com/#website"},
                "dateModified": modified.isoformat(),
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "FootballAnt", "item": "https://www.footballant.com/"},
                    {"@type": "ListItem", "position": 2, "name": "Match News", "item": BASE_URL},
                    {"@type": "ListItem", "position": 3, "name": name, "item": url},
                ],
            },
            {
                "@type": "ItemList",
                "name": f"{name} for {date_text}",
                "itemListElement": [
                    {"@type": "ListItem", "position": idx, "url": f"{BASE_URL}matches/{entry['slug']}/", "name": entry["title"]}
                    for idx, entry in enumerate(entries, start=1)
                ],
            },
            {"@type": "ImageObject", "url": IMAGE_URL, "width": 1200, "height": 675},
        ],
    }
    return '<script type="application/ld+json">' + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "</script>"


def render_hub(kind: str, target_date, entries: list[dict], modified: datetime) -> str:
    date_iso = target_date.isoformat()
    label = kind.title()
    title = f"{label} football lineups and predicted XI | FootballAnt"
    desc = f"Find {kind} football lineups for {date_iso}, including predicted XIs, team news, injury notes and score predictions before kickoff."
    empty = f"No {kind} lineup predictions are currently available for {date_iso}. Check the latest football lineup predictions page for newly published previews."
    body = item_list(entries) if entries else f"<p>{esc(empty)}</p>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}" />
  <meta name="robots" content="{ROBOTS}" />
  <link rel="canonical" href="{BASE_URL}{kind}-football-lineups/" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{esc(title)}" />
  <meta property="og:description" content="{esc(desc)}" />
  <meta property="og:url" content="{BASE_URL}{kind}-football-lineups/" />
  <meta property="og:image" content="{IMAGE_URL}" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{esc(title)}" />
  <meta name="twitter:description" content="{esc(desc)}" />
  <meta name="twitter:image" content="{IMAGE_URL}" />
  <link rel="stylesheet" href="../styles.css" />
  {hub_json_ld(kind, date_iso, entries, modified)}
</head>
<body class="match-news-home">
  <main>
    <header>
      <p class="kicker">FootballAnt Match News</p>
      <h1>{esc(title)}</h1>
      <p class="answer">Calibrated for {date_iso} Asia/Shanghai. Browse predicted XIs, team news and match predictions for this date.</p>
    </header>
    <section aria-labelledby="list-heading" itemscope itemtype="https://schema.org/ItemList">
      <h2 id="list-heading">{label} lineup predictions for {date_iso}</h2>
      <ol class="match-list">
{body}
      </ol>
    </section>
    <section>
      <h2>More football lineup predictions</h2>
      <ul>
        <li><a href="../">Football lineup predictions homepage</a></li>
        <li><a href="../latest-football-lineup-predictions/">Latest football lineup predictions</a></li>
      </ul>
    </section>
  </main>
</body>
</html>
"""


def update_sitemap_hub_lastmods(root: Path, lastmod: str) -> None:
    path = root / "sitemap.xml"
    if not path.exists():
        return
    text = read_text(path)
    targets = [
        BASE_URL,
        BASE_URL + "today-football-lineups/",
        BASE_URL + "tomorrow-football-lineups/",
    ]
    for url in targets:
        pattern = re.compile(r"(<loc>" + re.escape(url) + r"</loc>\s*<lastmod>)([^<]+)(</lastmod>)")
        text = pattern.sub(r"\g<1>" + lastmod + r"\g<3>", text, count=1)
    path.write_text(text, encoding="utf-8")


def homepage_json_ld(root: Path, entries: list[dict], modified: datetime) -> None:
    path = root / "index.html"
    text = read_text(path)
    top = entries[:60]
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "@id": "https://www.footballant.com/#website", "url": "https://www.footballant.com/", "name": "FootballAnt"},
            {"@type": "BreadcrumbList", "@id": f"{BASE_URL}#breadcrumb", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "FootballAnt", "item": "https://www.footballant.com/"},
                {"@type": "ListItem", "position": 2, "name": "Match News", "item": BASE_URL},
            ]},
            {"@type": "CollectionPage", "@id": f"{BASE_URL}#webpage", "url": BASE_URL, "name": "Football lineups, predicted XI and team news before kickoff", "description": "FootballAnt Match News collects calibrated football lineups, predicted XIs, team news, injury updates and league entry pages for pre-match football searches.", "isPartOf": {"@id": "https://www.footballant.com/#website"}, "breadcrumb": {"@id": f"{BASE_URL}#breadcrumb"}, "primaryImageOfPage": {"@id": f"{BASE_URL}#primaryimage"}, "dateModified": modified.isoformat(), "mainEntity": {"@id": f"{BASE_URL}#next-lineups"}},
            {"@type": "ImageObject", "@id": f"{BASE_URL}#primaryimage", "url": IMAGE_URL, "width": 1200, "height": 675},
            {"@type": "ItemList", "@id": f"{BASE_URL}#next-lineups", "name": "Next kickoff football lineup predictions", "itemListElement": [
                {"@type": "ListItem", "position": idx, "url": f"{BASE_URL}matches/{entry['slug']}/", "name": entry["title"], "description": f"{entry['league']} lineup prediction, team news and score prediction."}
                for idx, entry in enumerate(top, start=1)
            ]},
        ],
    }
    script = '<script type="application/ld+json">' + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "</script>"
    text = re.sub(r'<script type="application/ld\+json">.*?</script>', script, text, count=1, flags=re.S)
    path.write_text(text, encoding="utf-8")


def calibrate(root: Path, today, modified: datetime) -> dict:
    records = page_records(root)
    by_today = [r for r in records if r["date"] == today]
    by_tomorrow = [r for r in records if r["date"] == today + timedelta(days=1)]
    # Keep homepage structured data aligned with visible next-kickoff list: prefer today+, then recent fallback.
    homepage_entries = [r for r in records if r["date"] >= today][:60] or records[-60:]
    homepage_json_ld(root, homepage_entries, modified)
    update_sitemap_hub_lastmods(root, today.isoformat())
    for kind, target, entries in (("today", today, by_today), ("tomorrow", today + timedelta(days=1), by_tomorrow)):
        out = root / f"{kind}-football-lineups" / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_hub(kind, target, entries[:120], modified), encoding="utf-8")
    return {"root": str(root), "today": today.isoformat(), "today_count": len(by_today), "tomorrow_count": len(by_tomorrow), "homepage_structured_items": len(homepage_entries)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", required=True, help="publish/deploy root to calibrate")
    parser.add_argument("--date", required=True, help="Asia/Shanghai date YYYY-MM-DD; required for fail-closed time calibration")
    args = parser.parse_args()
    now = datetime.now(TZ)
    today = datetime.strptime(args.date, "%Y-%m-%d").date()
    results = [calibrate(Path(root), today, now) for root in args.root]
    print(json.dumps({"status": "ok", "generated_at": now.isoformat(), "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
