#!/usr/bin/env python3
"""Add market/fan/media watch modules to FootballAnt Match News.

This is intentionally framed as watchlist/context, not fabricated consensus.
It creates short, extractable sections that make each page feel closer to an
intelligence feed while avoiding unsupported claims.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
BASE = "https://www.footballant.com/match-news/"
SECTION_RE = re.compile(r'\s*<section class="market-context-section">.*?</section>', re.S)
HOME_RE = re.compile(r'\s*<!-- market-watch:start -->.*?<!-- market-watch:end -->', re.S)

BIG_CLUBS = (
    "Arsenal", "Chelsea", "Liverpool", "Manchester United", "Manchester City", "Tottenham", "Real Madrid", "Barcelona",
    "Atletico Madrid", "Paris Saint-Germain", "Bayern", "Dortmund", "Juventus", "Inter Milan", "AC Milan", "Napoli",
    "Roma", "Benfica", "Sporting", "Celtic", "Rangers"
)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def clean(value: str) -> str:
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


def parse_probability(text: str) -> str | None:
    m = re.search(r"Win probability:\s*([^<.]+)\.", text)
    return clean(m.group(1)) if m else None


def source_names(text: str) -> list[str]:
    block = re.search(r'<section class="sources-section">\s*<h2>Sources:</h2>\s*<ul>(.*?)</ul>', text, re.S)
    if not block:
        return []
    names = []
    for label in re.findall(r"<a [^>]*>(.*?)</a>", block.group(1), re.S):
        name = clean(label)
        if name and name not in names:
            names.append(name)
    return names[:10]


def page_record(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    title = clean((re.search(r"<title>(.*?)</title>", text, re.S) or [None, ""])[1])
    h1 = clean((re.search(r"<h1>(.*?)</h1>", text, re.S) or [None, title])[1])
    if not title:
        return None
    teams = re.match(r"(.+?) vs (.+?) (?:predicted lineup|lineups)", h1, re.I)
    home, away = (teams.group(1), teams.group(2)) if teams else ("Home team", "Away team")
    league = clean((re.search(r"<li><strong>Competition:</strong>\s*([^<]+)</li>", text, re.S) or [None, "football"])[1]) or "football"
    return {
        "slug": path.parent.name,
        "path": path,
        "text": text,
        "title": html.unescape(title),
        "home": html.unescape(home),
        "away": html.unescape(away),
        "league": html.unescape(league),
        "date": parse_date(title) or parse_date(h1),
        "probability": parse_probability(text),
        "sources": source_names(text),
    }


def interest_score(rec: dict) -> tuple[int, str]:
    text = f"{rec['title']} {rec['league']}"
    score = 0
    reasons = []
    for club in BIG_CLUBS:
        if club.lower() in text.lower():
            score += 8
            reasons.append("major-club interest")
            break
    if re.search(r"Premier League|La Liga|Serie A|Bundesliga|Champions League|Europa League", text, re.I):
        score += 5
        reasons.append("top-league context")
    if rec.get("sources"):
        score += min(5, len(rec["sources"]))
        reasons.append("source activity")
    if rec.get("date"):
        delta = (rec["date"] - datetime.now(TZ).date()).days
        if 0 <= delta <= 1:
            score += 6
            reasons.append("near kickoff")
        elif 2 <= delta <= 3:
            score += 3
    return score, ", ".join(dict.fromkeys(reasons)) or "lineup uncertainty"


def market_context(rec: dict) -> str:
    home = rec["home"]
    away = rec["away"]
    league = rec["league"]
    probability = rec.get("probability")
    source_names_text = ", ".join(rec.get("sources", [])[:4]) or "FootballAnt match data and public news discovery"
    score, reason = interest_score(rec)
    confidence = "high" if score >= 14 else "medium" if score >= 8 else "watchlist"
    prob_line = f"FootballAnt's current probability line is {probability}." if probability else "FootballAnt keeps the market read cautious until final lineups are clearer."
    return f'''          <section class="market-context-section">
            <h2>Market Sentiment</h2>
            <p>{esc(prob_line)} The main market question is whether late team news changes the expected XI or pushes the match away from the baseline prediction.</p>
            <p>Market watch level: {esc(confidence)} — driven by {esc(reason)}.</p>

            <h2>Fan Discussion Points</h2>
            <p>Supporter discussion is most likely to focus on the confirmed starting XI, any late injury or suspension news, and whether {esc(home)} can control the match state against {esc(away)}.</p>
            <p>For {esc(league)} searches, lineup uncertainty matters more than generic form talk because one confirmed absence can change the prediction quickly.</p>

            <h2>Media Watch</h2>
            <p>FootballAnt monitors public news and source channels before kickoff, including {esc(source_names_text)}.</p>
            <p>External reports are treated as context until they clearly confirm a player, injury, suspension or coach decision.</p>
          </section>'''


def patch_page(rec: dict) -> bool:
    text = SECTION_RE.sub("", rec["text"])
    section = market_context(rec)
    if "external-view-section" in text:
        new = re.sub(r'(\n\s*<section class="external-view-section">)', "\n" + section + r"\1", text, count=1)
    elif "<h2>Prediction</h2>" in text:
        new = re.sub(r'(\n\s*<section>\s*\n\s*<h2>Prediction</h2>)', "\n" + section + r"\1", text, count=1)
    else:
        return False
    if new != rec["text"]:
        rec["path"].write_text(new, encoding="utf-8")
        return True
    return False


def load_records(root: Path) -> list[dict]:
    records = []
    for path in (root / "matches").glob("*/index.html"):
        rec = page_record(path)
        if rec:
            records.append(rec)
    return records


def module_item(rec: dict) -> str:
    _, reason = interest_score(rec)
    return f'<li><a href="matches/{esc(rec["slug"])}/">{esc(rec["title"])}</a><span>{esc(reason)}.</span></li>'


def homepage_block(records: list[dict]) -> str:
    today = datetime.now(TZ).date()
    future = [r for r in records if not r.get("date") or r["date"] >= today]
    picks = sorted(future, key=lambda r: (-interest_score(r)[0], r.get("date") or today, r["title"]))[:6]
    if not picks:
        return ""
    return "\n".join([
        '<!-- market-watch:start -->',
        '    <section class="editorial-modules market-watch-home" aria-labelledby="market-watch-heading">',
        '      <div class="section-heading-row">',
        '        <div>',
        '          <p class="kicker">Football intelligence feed</p>',
        '          <h2 id="market-watch-heading">What The Market Is Watching Today</h2>',
        '        </div>',
        '        <a class="section-cta" href="latest-football-lineup-predictions/">Latest updates</a>',
        '      </div>',
        '      <p>A quick read on fixtures where lineup uncertainty, major-club interest, source activity or near-kickoff timing can move the prediction.</p>',
        '      <ul class="spotlight-grid">',
        *["        " + module_item(rec) for rec in picks],
        '      </ul>',
        '    </section>',
        '<!-- market-watch:end -->',
    ])


def patch_home(root: Path, records: list[dict]) -> bool:
    path = root / "index.html"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    block = homepage_block(records)
    if not block:
        return False
    stripped = HOME_RE.sub("", text)
    if "<!-- editorial-modules:start -->" in stripped:
        new = stripped.replace("<!-- editorial-modules:start -->", block + "\n\n<!-- editorial-modules:start -->", 1)
    elif '<section id="next-kickoff-lineups"' in stripped:
        new = stripped.replace('<section id="next-kickoff-lineups"', block + "\n\n    <section id=\"next-kickoff-lineups\"", 1)
    else:
        new = stripped.replace("</header>", "</header>\n\n" + block, 1)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def optimize(root: Path) -> dict:
    records = load_records(root)
    pages = sum(1 for rec in records if patch_page(rec))
    home = patch_home(root, records)
    return {"root": str(root), "records": len(records), "pages_patched": pages, "homepage_patched": home}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", required=True)
    args = parser.parse_args()
    results = [optimize(Path(root)) for root in args.root]
    print(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
