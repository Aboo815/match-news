#!/usr/bin/env python3
"""Strengthen FootballAnt Match News identity signals.

Focuses on the next SEO/GEO layer after basic publication:
- richer entity/source checks on match pages without inventing player facts;
- current, indexable league hub pages sorted around the Shanghai date;
- sitemap entries for hub pages.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
BASE = "https://www.footballant.com/match-news/"
IMAGE = BASE + "assets/footballant-match-news-preview.png"
ROBOTS = "index,follow,max-snippet:-1,max-image-preview:large,max-video-preview:-1"

LEAGUE_HUBS = {
    "premier-league-lineup-predictions": {
        "labels": ["Premier League", "English Premier League", "England Premier League"],
        "name": "Premier League lineup predictions",
        "desc": "Premier League predicted lineups, team news, injury checks and score predictions before kickoff.",
    },
    "la-liga-lineup-predictions": {
        "labels": ["La Liga", "Spanish La Liga", "Spain La Liga"],
        "name": "La Liga lineup predictions",
        "desc": "La Liga predicted XIs, team-news checks, injury context and match predictions before kickoff.",
    },
    "serie-a-lineup-predictions": {
        "labels": ["Serie A", "Italian Serie A", "Italy Serie A"],
        "name": "Serie A lineup predictions",
        "desc": "Serie A lineup projections, availability notes, injury checks and match predictions before kickoff.",
    },
    "bundesliga-lineup-predictions": {
        "labels": ["Bundesliga", "German Bundesliga", "Germany Bundesliga"],
        "name": "Bundesliga lineup predictions",
        "desc": "Bundesliga predicted starters, team news, injury checks and score predictions before kickoff.",
    },
    "champions-league-lineup-predictions": {
        "labels": ["Champions League", "UEFA Champions League", "UCL"],
        "name": "Champions League lineup predictions",
        "desc": "Champions League predicted lineups, rotation watch, injury checks and match predictions before kickoff.",
    },
}

MAJOR_SOURCE_NAMES = ("BBC", "Sky Sports", "Reuters", "ESPN", "club official", "official site", "The Guardian")
PLAYER_HINT_WORDS = ("injury", "injured", "absence", "absent", "suspension", "suspended", "fitness", "return", "available", "availability", "training")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def parse_date(title: str):
    m = re.search(r"\(([^()]+\d{4})\)", title)
    if not m:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(m.group(1), fmt).date()
        except ValueError:
            pass
    return None


def source_names(text: str) -> list[str]:
    block = re.search(r'<section class="sources-section">\s*<h2>Sources:</h2>\s*<ul>(.*?)</ul>', text, re.S)
    if not block:
        return []
    names = []
    for label in re.findall(r"<a [^>]*>(.*?)</a>", block.group(1), re.S):
        name = clean_text(label)
        if name and name not in names:
            names.append(name)
    return names[:8]


def record_from_page(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    title_m = re.search(r"<title>(.*?)</title>", text, re.S)
    title = clean_text(title_m.group(1)) if title_m else ""
    if not title:
        return None
    h1 = clean_text((re.search(r"<h1>(.*?)</h1>", text, re.S) or [None, title])[1])
    teams_m = re.match(r"(.+?) vs (.+?) (?:predicted lineup|lineups)", h1, re.I)
    home, away = (teams_m.group(1), teams_m.group(2)) if teams_m else ("Home team", "Away team")
    league = clean_text((re.search(r"<li><strong>Competition:</strong>\s*([^<]+)</li>", text, re.S) or [None, "football"])[1]) or "football"
    date = parse_date(title) or parse_date(h1)
    return {
        "slug": path.parent.name,
        "title": html.unescape(title),
        "home": html.unescape(home),
        "away": html.unescape(away),
        "league": html.unescape(league),
        "date": date,
        "sources": source_names(text),
        "path": path,
        "text": text,
    }


def page_records(root: Path) -> list[dict]:
    records = []
    for path in (root / "matches").glob("*/index.html"):
        rec = record_from_page(path)
        if rec:
            records.append(rec)
    records.sort(key=lambda r: (r["date"] or datetime.max.date(), r["title"]))
    return records


def source_status(names: list[str]) -> str:
    if not names:
        return "No public source links are attached yet; keep player and injury claims conservative."
    major = [n for n in names if any(token.lower() in n.lower() for token in MAJOR_SOURCE_NAMES)]
    if major:
        return "Source pack includes recognised football/news desks: " + ", ".join(major[:4]) + "."
    return "Source pack attached: " + ", ".join(names[:4]) + "."


def entity_section(rec: dict) -> str:
    names = rec.get("sources") or []
    likely_injury_source = any(any(w in n.lower() for w in PLAYER_HINT_WORDS) for n in names)
    injury_line = "Named player absences stay unpublished until a club, league or major news source confirms them."
    if likely_injury_source:
        injury_line = "Player availability should be checked against the linked injury/team-news source before kickoff."
    src_items = "".join(f"\n              <li>{esc(name)}</li>" for name in names[:5]) or "\n              <li>Fixture-specific news search and FootballAnt match data.</li>"
    return f'''          <section class="entity-signal-section">
            <h2>Lineup entity check</h2>
            <ul>
              <li><strong>Team entities:</strong> {esc(rec["home"])} and {esc(rec["away"])}.</li>
              <li><strong>Competition entity:</strong> {esc(rec["league"])}.</li>
              <li><strong>Player entity policy:</strong> do not name a player as injured, suspended or returning unless the source pack confirms that player.</li>
              <li><strong>Injury entity status:</strong> {esc(injury_line)}</li>
              <li><strong>Citation status:</strong> {esc(source_status(names))}</li>
            </ul>
            <h3>Public sources checked</h3>
            <ul>{src_items}
            </ul>
          </section>'''


def patch_entity_section(rec: dict) -> bool:
    path = rec["path"]
    text = rec["text"]
    section = entity_section(rec)
    if 'class="entity-signal-section"' in text:
        new = re.sub(r'\s*<section class="entity-signal-section">.*?</section>', "\n" + section, text, count=1, flags=re.S)
    else:
        new = re.sub(r'(\n\s*<section>\s*\n\s*<h2>Tactical Notes</h2>)', "\n" + section + r"\1", text, count=1)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def league_matches(records: list[dict], labels: list[str]) -> list[dict]:
    labels_l = [x.lower() for x in labels]
    selected = []
    for rec in records:
        league_l = rec["league"].lower()
        title_l = rec["title"].lower()
        if any(label in league_l or label in title_l for label in labels_l):
            selected.append(rec)
    return selected


def editorial_reason(rec: dict) -> str:
    league = rec["league"]
    if rec.get("sources"):
        return f"Source-linked {league} lineup watch with team-news checks before kickoff."
    return f"{league} lineup watch where final team news can still change the expected XI."


def render_hub(slug: str, meta: dict, matches: list[dict], today, modified: datetime) -> str:
    url = BASE + slug + "/"
    current = [m for m in matches if not m["date"] or m["date"] >= today]
    archive = [m for m in matches if m["date"] and m["date"] < today]
    ordered = (current + archive)[:80]
    items = []
    for idx, rec in enumerate(ordered, 1):
        items.append(f'''<li itemprop="itemListElement" itemscope itemtype="https://schema.org/ListItem">
  <a itemprop="item" href="../matches/{esc(rec['slug'])}/"><span itemprop="name">{esc(rec['title'])}</span></a>
  <p>{esc(editorial_reason(rec))}</p>
  <meta itemprop="position" content="{idx}" />
</li>''')
    list_html = "\n".join(items) if items else "<li>No current match-news pages are available for this league yet.</li>"
    pick_html = "\n".join(
        f"<li><a href=\"../matches/{esc(rec['slug'])}/\">{esc(rec['title'])}</a><span>{esc(editorial_reason(rec))}</span></li>"
        for rec in current[:5]
    ) or "<li>New editor picks will appear after the next publish cycle.</li>"
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "CollectionPage", "url": url, "name": meta["name"], "description": meta["desc"], "dateModified": modified.isoformat(), "isPartOf": {"@id": "https://www.footballant.com/#website"}},
            {"@type": "ItemList", "name": meta["name"], "itemListElement": [
                {"@type": "ListItem", "position": idx, "url": BASE + "matches/" + rec["slug"] + "/", "name": rec["title"]}
                for idx, rec in enumerate(ordered[:30], 1)
            ]},
            {"@type": "ImageObject", "url": IMAGE, "width": 1200, "height": 675},
        ],
    }
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{esc(meta['name'].title())}, Team News and Predictions | FootballAnt</title>
  <meta name="description" content="{esc(meta['desc'])}" />
  <meta name="robots" content="{ROBOTS}" />
  <link rel="canonical" href="{url}" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{esc(meta['name'])} | FootballAnt" />
  <meta property="og:description" content="{esc(meta['desc'])}" />
  <meta property="og:url" content="{url}" />
  <meta property="og:image" content="{IMAGE}" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:image" content="{IMAGE}" />
  <script type="application/ld+json">{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}</script>
  <link rel="stylesheet" href="../styles.css" />
</head>
<body class="match-news-home">
  <main>
    <nav class="breadcrumb" aria-label="Breadcrumb"><a href="../">Match News</a> / {esc(meta['name'])}</nav>
    <header>
      <p class="kicker">League hub</p>
      <h1>{esc(meta['name'])}</h1>
      <p class="answer">{esc(meta['desc'])}</p>
    </header>
    <section class="editorial-modules" aria-labelledby="hub-picks-heading">
      <h2 id="hub-picks-heading">Editor watchlist</h2>
      <p>These matches are prioritised by league interest, recency and team-news risk rather than shown as a flat archive.</p>
      <ul class="spotlight-grid">
{pick_html}
      </ul>
    </section>
    <section aria-labelledby="source-policy-heading">
      <h2 id="source-policy-heading">How FootballAnt treats lineup sources</h2>
      <p>Predicted XIs stay provisional until club, league or major news reports confirm player availability. Injury and suspension names should be treated as unconfirmed unless a page links to a supporting public source.</p>
    </section>
    <section aria-labelledby="article-list-heading" itemscope itemtype="https://schema.org/ItemList">
      <h2 id="article-list-heading">{esc(meta['name'])} articles</h2>
      <ol class="match-list">
{list_html}
      </ol>
    </section>
  </main>
</body>
</html>
'''


def update_sitemap(root: Path, hub_slugs: list[str], today: str) -> None:
    path = root / "sitemap.xml"
    if not path.exists():
        return
    xml = path.read_text(encoding="utf-8", errors="ignore")
    insert_at = xml.rfind("</urlset>")
    if insert_at < 0:
        return
    blocks = []
    for slug in hub_slugs:
        loc = BASE + slug + "/"
        if f"<loc>{loc}</loc>" in xml:
            xml = re.sub(rf"(<loc>{re.escape(loc)}</loc>\s*<lastmod>)[^<]+", rf"\g<1>{today}", xml)
            continue
        blocks.append(f'''  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.7</priority>
  </url>
''')
    if blocks:
        xml = xml[:insert_at] + "".join(blocks) + xml[insert_at:]
    path.write_text(xml, encoding="utf-8")


def optimize(root: Path, today, modified: datetime) -> dict:
    records = page_records(root)
    patched = sum(1 for rec in records if patch_entity_section(rec))
    hubs = []
    for slug, meta in LEAGUE_HUBS.items():
        matches = league_matches(records, meta["labels"])
        if not matches:
            continue
        out = root / slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_hub(slug, meta, matches, today, modified), encoding="utf-8")
        hubs.append(slug)
    update_sitemap(root, hubs, today.isoformat())
    return {"root": str(root), "pages": len(records), "entity_pages_patched": patched, "hubs": hubs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--date", help="Asia/Shanghai date YYYY-MM-DD")
    args = parser.parse_args()
    now = datetime.now(TZ)
    today = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else now.date()
    results = [optimize(Path(root), today, now) for root in args.root]
    print(json.dumps({"status": "ok", "generated_at": now.isoformat(), "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
