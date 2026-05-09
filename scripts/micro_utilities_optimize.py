#!/usr/bin/env python3
"""Generate low-cost FootballAnt micro utility pages.

Pages are static, indexable and driven by existing Match Signals rather than
fabricated user/vote data:
- Today's Most Stable Matches
- Fan Mood Index
- Match Fortune Today
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
IMAGE = BASE + "assets/footballant-match-news-preview.png"
ROBOTS = "index,follow,max-snippet:-1,max-image-preview:large,max-video-preview:-1"
HOME_RE = re.compile(r'\s*<!-- micro-utilities:start -->.*?<!-- micro-utilities:end -->', re.S)


def esc(v: object) -> str:
    return html.escape(str(v), quote=True)


def clean(v: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", v or "")).strip()


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


def signals(text: str) -> dict[str, tuple[str, int]]:
    out = {}
    for row in re.findall(r'<tr>\s*<th scope="row">(.*?)</th>\s*<td>(.*?)</td>\s*<td>(\d+)/100</td>', text, re.S):
        out[clean(row[0])] = (clean(row[1]), int(row[2]))
    return out


def page_record(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    title = clean((re.search(r"<title>(.*?)</title>", text, re.S) or [None, ""])[1])
    h1 = clean((re.search(r"<h1>(.*?)</h1>", text, re.S) or [None, title])[1])
    if not title:
        return None
    teams = re.match(r"(.+?) vs (.+?) (?:predicted lineup|lineups)", h1, re.I)
    home, away = (teams.group(1), teams.group(2)) if teams else ("Home team", "Away team")
    league = clean((re.search(r"<li><strong>Competition:</strong>\s*([^<]+)</li>", text, re.S) or [None, "football"])[1]) or "football"
    sig = signals(text)
    return {
        "slug": path.parent.name,
        "title": html.unescape(title),
        "home": html.unescape(home),
        "away": html.unescape(away),
        "league": html.unescape(league),
        "date": parse_date(title) or parse_date(h1),
        "signals": sig,
        "has_external": 'external-view-section' in text,
    }


def records(root: Path) -> list[dict]:
    out = []
    for path in (root / "matches").glob("*/index.html"):
        rec = page_record(path)
        if rec:
            out.append(rec)
    return out


def sig_score(rec: dict, name: str, default: int = 50) -> int:
    return rec.get("signals", {}).get(name, ("", default))[1]


def sig_label(rec: dict, name: str, default: str = "Medium") -> str:
    return rec.get("signals", {}).get(name, (default, 50))[0]


def stable_score(rec: dict) -> int:
    return max(0, min(100, sig_score(rec, "Lineup Certainty") + sig_score(rec, "Tactical Stability") // 2 - sig_score(rec, "Injury Pressure") // 3 - sig_score(rec, "Odds Volatility Watch") // 4))


def mood_score(rec: dict) -> int:
    base = sig_score(rec, "Market Confidence")
    base += 8 if rec.get("has_external") else 0
    base -= sig_score(rec, "Injury Pressure") // 5
    return max(0, min(100, base))


def fortune_score(rec: dict) -> int:
    base = stable_score(rec) // 2 + sig_score(rec, "Market Confidence") // 2
    base -= sig_score(rec, "Rotation Risk") // 6
    return max(0, min(100, base))


def page_shell(slug: str, title: str, desc: str, body: str, item_list: list[dict] | None = None) -> str:
    url = BASE + slug + "/"
    graph = [
        {"@type": "WebPage", "url": url, "name": title, "description": desc, "dateModified": datetime.now(TZ).isoformat()},
        {"@type": "ImageObject", "url": IMAGE, "width": 1200, "height": 675},
    ]
    if item_list:
        graph.append({"@type": "ItemList", "name": title, "itemListElement": [
            {"@type": "ListItem", "position": i, "url": BASE + "matches/" + r["slug"] + "/", "name": r["title"]}
            for i, r in enumerate(item_list[:30], 1)
        ]})
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{esc(title)} | FootballAnt</title>
  <meta name="description" content="{esc(desc)}" />
  <meta name="robots" content="{ROBOTS}" />
  <link rel="canonical" href="{url}" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{esc(title)} | FootballAnt" />
  <meta property="og:description" content="{esc(desc)}" />
  <meta property="og:url" content="{url}" />
  <meta property="og:image" content="{IMAGE}" />
  <meta name="twitter:card" content="summary_large_image" />
  <script type="application/ld+json">{json.dumps({"@context":"https://schema.org","@graph":graph}, ensure_ascii=False, separators=(',', ':'))}</script>
  <link rel="stylesheet" href="../styles.css" />
</head>
<body class="match-news-home">
  <main>
    <nav class="breadcrumb"><a href="../">Match News</a> / {esc(title)}</nav>
    <header>
      <p class="kicker">FootballAnt micro tool</p>
      <h1>{esc(title)}</h1>
      <p class="answer">{esc(desc)}</p>
    </header>
{body}
  </main>
</body>
</html>
'''


def match_link(rec: dict, note: str) -> str:
    return f'<li><a href="../matches/{esc(rec["slug"])}/">{esc(rec["title"])}</a><span>{esc(note)}</span></li>'


def stable_page(recs: list[dict], today) -> tuple[str, str, str, list[dict]]:
    current = [r for r in recs if not r.get("date") or r["date"] >= today]
    ranked = sorted(current, key=lambda r: (-stable_score(r), r.get("date") or today, r["title"]))[:30]
    rows = []
    for r in ranked:
        rows.append(f'''<tr><td><a href="../matches/{esc(r['slug'])}/">{esc(r['title'])}</a></td><td>{stable_score(r)}/100</td><td>{esc(sig_label(r, 'Lineup Certainty'))}</td><td>{esc(sig_label(r, 'Injury Pressure'))}</td><td>{esc(sig_label(r, 'Odds Volatility Watch'))}</td></tr>''')
    body = f'''    <section>
      <h2>Today's Most Stable Matches</h2>
      <p>Ranked by lineup certainty, tactical stability, injury pressure and volatility watch. This is a football stability signal, not betting advice.</p>
      <table><thead><tr><th>Match</th><th>Stable Index</th><th>Lineup Certainty</th><th>Injury Pressure</th><th>Volatility Watch</th></tr></thead><tbody>
{chr(10).join(rows)}
      </tbody></table>
    </section>'''
    return "todays-most-stable-matches", "Today's Most Stable Matches", "A daily FootballAnt stability board for football matches with stronger lineup certainty and lower risk signals.", body, ranked


def mood_page(recs: list[dict], today) -> tuple[str, str, str, list[dict]]:
    current = [r for r in recs if not r.get("date") or r["date"] >= today]
    ranked = sorted(current, key=lambda r: (-mood_score(r), -sig_score(r, "Market Confidence"), r["title"]))[:30]
    rows = []
    for r in ranked:
        mood = mood_score(r)
        label = "Confident" if mood >= 70 else "Nervous but active" if mood >= 50 else "Cautious"
        rows.append(f'''<tr><td><a href="../matches/{esc(r['slug'])}/">{esc(r['title'])}</a></td><td>{mood}/100</td><td>{label}</td><td>{esc(sig_label(r, 'Market Confidence'))}</td><td>{esc(sig_label(r, 'Injury Pressure'))}</td></tr>''')
    body = f'''    <section>
      <h2>Fan Mood Index</h2>
      <p>A light football mood board based on market attention, source activity and injury pressure. It is a sentiment proxy, not a fan poll.</p>
      <table><thead><tr><th>Match</th><th>Mood Index</th><th>Mood</th><th>Market Confidence</th><th>Injury Pressure</th></tr></thead><tbody>
{chr(10).join(rows)}
      </tbody></table>
    </section>'''
    return "fan-mood-index", "Fan Mood Index", "A football fan mood and pressure board generated from FootballAnt match signals, source activity and injury pressure.", body, ranked


def fortune_page(recs: list[dict], today) -> tuple[str, str, str, list[dict]]:
    current = [r for r in recs if not r.get("date") or r["date"] >= today]
    ranked = sorted(current, key=lambda r: (-fortune_score(r), r.get("date") or today, r["title"]))[:24]
    cards = []
    for r in ranked:
        score = fortune_score(r)
        fortune = "Lucky draw" if score >= 75 else "Good signs" if score >= 60 else "Chaotic watch" if score >= 45 else "High-risk mood"
        cards.append(match_link(r, f"Match fortune: {score}/100 · {fortune} · Rotation Risk {sig_label(r, 'Rotation Risk')}"))
    body = f'''    <section class="editorial-modules">
      <h2>Match Fortune Today</h2>
      <p>A shareable, lightweight football mood tool: it blends stability, market confidence and rotation risk into a daily match-fortune read.</p>
      <ul class="spotlight-grid">
{chr(10).join(cards)}
      </ul>
    </section>'''
    return "match-fortune-today", "Match Fortune Today", "A light, shareable football match fortune board powered by FootballAnt signals, lineup certainty and market confidence.", body, ranked


def update_sitemap(root: Path, slugs: list[str], today: str) -> None:
    path = root / "sitemap.xml"
    if not path.exists():
        return
    xml = path.read_text(encoding="utf-8", errors="ignore")
    insert = xml.rfind("</urlset>")
    if insert < 0:
        return
    blocks = []
    for slug in slugs:
        loc = BASE + slug + "/"
        if f"<loc>{loc}</loc>" in xml:
            xml = re.sub(rf"(<loc>{re.escape(loc)}</loc>\s*<lastmod>)[^<]+", rf"\g<1>{today}", xml)
        else:
            blocks.append(f'''  <url>\n    <loc>{loc}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.7</priority>\n  </url>\n''')
    if blocks:
        xml = xml[:insert] + "".join(blocks) + xml[insert:]
    path.write_text(xml, encoding="utf-8")


def homepage_block() -> str:
    items = [
        ("Today's Most Stable Matches", "todays-most-stable-matches/", "Lineup certainty, injury stability and volatility watch."),
        ("Fan Mood Index", "fan-mood-index/", "A light sentiment proxy for football attention and pressure."),
        ("Match Fortune Today", "match-fortune-today/", "Shareable match fortune powered by FootballAnt signals."),
    ]
    cards = "\n".join(f'        <li><a href="{href}">{esc(label)}</a><span>{esc(note)}</span></li>' for label, href, note in items)
    return f'''<!-- micro-utilities:start -->
    <section class="editorial-modules micro-utilities" aria-labelledby="micro-tools-heading">
      <div class="section-heading-row">
        <div>
          <p class="kicker">Football micro tools</p>
          <h2 id="micro-tools-heading">Quick football tools for today</h2>
        </div>
      </div>
      <p>Small, searchable and shareable FootballAnt tools built from match signals rather than generic football copy.</p>
      <ul class="spotlight-grid">
{cards}
      </ul>
    </section>
<!-- micro-utilities:end -->'''


def patch_home(root: Path) -> bool:
    path = root / "index.html"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    block = homepage_block()
    stripped = HOME_RE.sub("", text)
    if "<!-- match-signals-home:start -->" in stripped:
        new = stripped.replace("<!-- match-signals-home:start -->", block + "\n\n<!-- match-signals-home:start -->", 1)
    elif "<!-- market-watch:start -->" in stripped:
        new = stripped.replace("<!-- market-watch:start -->", block + "\n\n<!-- market-watch:start -->", 1)
    else:
        new = stripped.replace("</header>", "</header>\n\n" + block, 1)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def optimize(root: Path) -> dict:
    recs = records(root)
    today = datetime.now(TZ).date()
    pages = [stable_page(recs, today), mood_page(recs, today), fortune_page(recs, today)]
    slugs = []
    for slug, title, desc, body, ranked in pages:
        out = root / slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page_shell(slug, title, desc, body, ranked), encoding="utf-8")
        slugs.append(slug)
    home = patch_home(root)
    update_sitemap(root, slugs, today.isoformat())
    return {"root": str(root), "records": len(recs), "pages": slugs, "homepage_patched": home}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", required=True)
    args = parser.parse_args()
    results = [optimize(Path(root)) for root in args.root]
    print(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
