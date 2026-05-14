#!/usr/bin/env python3
"""Add FootballAnt Match Signals to match-news pages.

These are heuristic, source-aware football intelligence signals. They avoid
pretending to be measured betting/fan data unless the page actually has a data
source; the goal is an extractable, branded decision layer.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
SECTION_RE = re.compile(r'\s*<section class="match-signals-section"[^>]*>.*?</section>', re.S)
HOME_RE = re.compile(r'\s*<!-- match-signals-home:start -->.*?<!-- match-signals-home:end -->', re.S)

BIG_CLUBS = (
    "Arsenal", "Chelsea", "Liverpool", "Manchester United", "Manchester City", "Tottenham", "Real Madrid", "Barcelona",
    "Atletico Madrid", "Paris Saint-Germain", "Bayern", "Dortmund", "Juventus", "Inter Milan", "AC Milan", "Napoli",
    "Roma", "Benfica", "Sporting", "Celtic", "Rangers"
)
TOP_LEAGUES = ("Premier League", "La Liga", "Serie A", "Bundesliga", "Champions League", "Europa League")


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


def source_count(text: str) -> int:
    block = re.search(r'<section class="sources-section">\s*<h2>Sources:</h2>\s*<ul>(.*?)</ul>', text, re.S)
    return len(re.findall(r"<li", block.group(1), re.S)) if block else 0


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
        "sources": source_count(text),
        "has_external": 'class="external-view-section"' in text,
        "has_market": 'class="market-context-section"' in text,
    }


def status(score: int) -> str:
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    if score >= 30:
        return "Moderate"
    return "Low"


def direction(score: int, reverse: bool = False) -> str:
    label = status(score)
    if reverse:
        return {"High": "Low", "Medium": "Medium", "Moderate": "Moderate", "Low": "High"}[label]
    return label


def scores(rec: dict) -> dict[str, tuple[str, int, str]]:
    text = f"{rec['title']} {rec['league']}"
    today = datetime.now(TZ).date()
    days = (rec["date"] - today).days if rec.get("date") else 3
    near = 25 if 0 <= days <= 1 else 15 if 2 <= days <= 3 else 5
    major = 18 if any(club.lower() in text.lower() for club in BIG_CLUBS) else 0
    top = 15 if any(league.lower() in text.lower() for league in TOP_LEAGUES) else 0
    src = min(25, rec.get("sources", 0) * 3)
    ext = 10 if rec.get("has_external") else 0
    market = 8 if rec.get("has_market") else 0

    rotation_risk = min(100, 34 + near + top // 2 + (10 if "cup" in text.lower() else 0))
    injury_pressure = min(100, 25 + src + ext + (8 if re.search(r"injur|suspension|absence|fitness", rec["text"], re.I) else 0))
    market_confidence = min(100, 30 + near + major + top + market)
    tactical_stability = max(15, 82 - rotation_risk // 2 - injury_pressure // 5)
    odds_volatility = min(100, 28 + near + injury_pressure // 3 + major // 2)
    lineup_certainty = max(10, 88 - rotation_risk // 2 - injury_pressure // 3)

    return {
        "Rotation Risk": (direction(rotation_risk), rotation_risk, "Late team news or schedule context may still alter the expected XI."),
        "Injury Pressure": (direction(injury_pressure), injury_pressure, "Availability signals and source activity are the main pre-kickoff watchpoint."),
        "Market Confidence": (direction(market_confidence), market_confidence, "Confidence reflects source depth, fixture attention and proximity to kickoff."),
        "Tactical Stability": (direction(tactical_stability), tactical_stability, "Lower stability means the prediction depends more on confirmed lineups."),
        "Odds Volatility Watch": (direction(odds_volatility), odds_volatility, "A watch signal only; FootballAnt does not claim a verified odds move unless a source confirms it."),
        "Lineup Certainty": (direction(lineup_certainty), lineup_certainty, "Certainty improves when official lineups, club updates or reliable injury reports are available."),
    }


def signal_section(rec: dict) -> str:
    rows = []
    for name, (label, score, note) in scores(rec).items():
        rows.append(f'''              <tr>
                <th scope="row">{esc(name)}</th>
                <td>{esc(label)}</td>
                <td>{score}/100</td>
                <td>{esc(note)}</td>
              </tr>''')
    prob = f" Current model line: {rec['probability']}." if rec.get("probability") else ""
    return f'''          <section class="match-signals-section" aria-labelledby="match-signals-heading">
            <h2 id="match-signals-heading">FootballAnt Match Signals</h2>
            <p>Fast football intelligence signals for {esc(rec['home'])} vs {esc(rec['away'])}.{esc(prob)} These indicators help readers judge lineup risk, injury pressure and prediction reliability before kickoff.</p>
            <table>
              <thead><tr><th>Signal</th><th>Status</th><th>Index</th><th>What it means</th></tr></thead>
              <tbody>
{chr(10).join(rows)}
              </tbody>
            </table>
          </section>'''


def patch_page(rec: dict) -> bool:
    text = SECTION_RE.sub("", rec["text"])
    section = signal_section(rec)
    if '<section class="key-facts">' in text:
        new = re.sub(r'(\n\s*<section class="key-facts">)', "\n" + section + r"\1", text, count=1)
    elif "</header>" in text:
        new = text.replace("</header>", "</header>\n\n" + section, 1)
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


def home_block(records: list[dict]) -> str:
    today = datetime.now(TZ).date()
    current = [r for r in records if not r.get("date") or r["date"] >= today]
    ranked = sorted(current, key=lambda r: (-scores(r)["Market Confidence"][1], -scores(r)["Injury Pressure"][1], r["title"]))[:5]
    if not ranked:
        return ""
    rows = []
    for rec in ranked:
        sig = scores(rec)
        rows.append(f'''        <li><a href="matches/{esc(rec['slug'])}/">{esc(rec['title'])}</a><span>Rotation Risk: {esc(sig['Rotation Risk'][0])} · Injury Pressure: {esc(sig['Injury Pressure'][0])} · Market Confidence: {esc(sig['Market Confidence'][0])}</span></li>''')
    return "\n".join([
        '<!-- match-signals-home:start -->',
        '    <section class="editorial-modules match-signals-home" aria-labelledby="signals-home-heading">',
        '      <h2 id="signals-home-heading">FootballAnt Match Signals</h2>',
        '      <p>Structured risk signals for fixtures where lineup changes, injury pressure or market attention can change the pre-match read.</p>',
        '      <ul class="spotlight-grid">',
        *rows,
        '      </ul>',
        '    </section>',
        '<!-- match-signals-home:end -->',
    ])


def patch_home(root: Path, records: list[dict]) -> bool:
    path = root / "index.html"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    block = home_block(records)
    if not block:
        return False
    stripped = HOME_RE.sub("", text)
    if "<!-- market-watch:start -->" in stripped:
        new = stripped.replace("<!-- market-watch:start -->", block + "\n\n<!-- market-watch:start -->", 1)
    elif "<!-- editorial-modules:start -->" in stripped:
        new = stripped.replace("<!-- editorial-modules:start -->", block + "\n\n<!-- editorial-modules:start -->", 1)
    else:
        new = stripped.replace("</header>", "</header>\n\n" + block, 1)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def optimize(root: Path) -> dict:
    records = load_records(root)
    patched = sum(1 for rec in records if patch_page(rec))
    home = patch_home(root, records)
    return {"root": str(root), "records": len(records), "pages_patched": patched, "homepage_patched": home}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", required=True)
    args = parser.parse_args()
    results = [optimize(Path(root)) for root in args.root]
    print(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
