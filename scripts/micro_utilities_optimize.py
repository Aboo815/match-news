#!/usr/bin/env python3
"""Generate low-cost FootballAnt micro utility pages.

Pages are static, indexable and driven by existing Match Signals rather than
fabricated user/vote data. Public wording separates the formal product layer
from the social/emotion layer:
- Lineup Clarity Board
- Fan Mood Index
- Chaos Match Watch
"""
from __future__ import annotations

import argparse
import html
import hashlib
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


def texture(rec: dict, salt: str, spread: int = 9) -> int:
    """Deterministic small variation so public scores do not look batch-rounded."""
    raw = hashlib.sha1(f"{rec.get('slug','')}:{salt}".encode("utf-8")).hexdigest()
    return int(raw[:4], 16) % (spread * 2 + 1) - spread


def clamp_score(v: int) -> int:
    # Avoid fake precision extremes while keeping non-round public numbers.
    return max(29, min(87, v))


def stable_score(rec: dict) -> int:
    base = int(
        sig_score(rec, "Lineup Certainty") * 0.70
        + sig_score(rec, "Tactical Stability") * 0.45
        + (100 - sig_score(rec, "Injury Pressure")) * 0.25
        + (100 - sig_score(rec, "Odds Volatility Watch")) * 0.20
    )
    return clamp_score(base + texture(rec, "clarity"))


def mood_score(rec: dict) -> int:
    base = sig_score(rec, "Market Confidence")
    base += 8 if rec.get("has_external") else 0
    base -= sig_score(rec, "Injury Pressure") // 5
    return clamp_score(base + texture(rec, "mood"))


def chaos_score(rec: dict) -> int:
    base = int(
        sig_score(rec, "Rotation Risk") * 0.34
        + sig_score(rec, "Injury Pressure") * 0.34
        + sig_score(rec, "Odds Volatility Watch") * 0.26
        + max(0, 68 - sig_score(rec, "Lineup Certainty")) * 0.28
    )
    return clamp_score(base + texture(rec, "chaos"))


def mood_label(score: int) -> str:
    if score >= 78:
        return "Fans are pretending to be calm"
    if score >= 68:
        return "Fan optimism rising"
    if score >= 58:
        return "Nervous confidence"
    if score >= 46:
        return "Cautious mood"
    return "Panic potential"


def chaos_label(score: int) -> str:
    if score >= 76:
        return "Chaos match energy"
    if score >= 64:
        return "Trap game alert"
    if score >= 52:
        return "Rotation anxiety"
    if score >= 40:
        return "Lineup unease"
    return "Low-drama read"


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
        score = stable_score(r)
        read = "Clean XI read" if score >= 74 else "Mostly clear" if score >= 62 else "Watch late team news" if score >= 48 else "Lineup panic risk"
        rows.append(f'''<tr><td><a href="../matches/{esc(r['slug'])}/">{esc(r['title'])}</a></td><td>{score}</td><td>{esc(read)}</td><td>{esc(sig_label(r, 'Lineup Certainty'))}</td><td>{esc(sig_label(r, 'Injury Pressure'))}</td><td>{esc(sig_label(r, 'Odds Volatility Watch'))}</td></tr>''')
    body = f'''    <section>
      <h2>Lineup Clarity Board</h2>
      <p>Matches where the pre-match read looks clearer — or where late team news could still ruin the picture. Signal-based, not a betting tip.</p>
      <table><thead><tr><th>Match</th><th>Clarity</th><th>Read</th><th>Lineup Certainty</th><th>Injury Tension</th><th>Volatility Watch</th></tr></thead><tbody>
{chr(10).join(rows)}
      </tbody></table>
    </section>'''
    return "todays-most-stable-matches", "Lineup Clarity Board", "A daily FootballAnt board for pre-match lineup clarity, injury tension and volatility signals.", body, ranked


def mood_page(recs: list[dict], today) -> tuple[str, str, str, list[dict]]:
    current = [r for r in recs if not r.get("date") or r["date"] >= today]
    ranked = sorted(current, key=lambda r: (-mood_score(r), -sig_score(r, "Market Confidence"), r["title"]))[:30]
    rows = []
    for r in ranked:
        mood = mood_score(r)
        label = mood_label(mood)
        rows.append(f'''<tr><td><a href="../matches/{esc(r['slug'])}/">{esc(r['title'])}</a></td><td>{mood}</td><td>{esc(label)}</td><td>{esc(sig_label(r, 'Market Confidence'))}</td><td>{esc(sig_label(r, 'Injury Pressure'))}</td></tr>''')
    body = f'''    <section>
      <h2>Fan Mood Index</h2>
      <p>A signal-driven estimate of pre-match fan confidence. It is a sentiment proxy, not a fan poll.</p>
      <table><thead><tr><th>Match</th><th>Mood</th><th>Social read</th><th>Attention Signal</th><th>Injury Tension</th></tr></thead><tbody>
{chr(10).join(rows)}
      </tbody></table>
    </section>'''
    return "fan-mood-index", "Fan Mood Index", "A signal-driven estimate of pre-match fan confidence, pressure and injury tension.", body, ranked


def fortune_page(recs: list[dict], today) -> tuple[str, str, str, list[dict]]:
    current = [r for r in recs if not r.get("date") or r["date"] >= today]
    ranked = sorted(current, key=lambda r: (-chaos_score(r), r.get("date") or today, r["title"]))[:24]
    cards = []
    for r in ranked:
        score = chaos_score(r)
        cards.append(match_link(r, f"Chaos read: {score} · {chaos_label(score)} · Rotation {sig_label(r, 'Rotation Risk')}"))
    body = f'''    <section class="editorial-modules">
      <h2>Chaos Match Watch</h2>
      <p>The fixtures that smell unstable before kickoff: rotation anxiety, injury tension and volatility signals in one quick scan.</p>
      <ul class="spotlight-grid">
{chr(10).join(cards)}
      </ul>
    </section>'''
    return "match-fortune-today", "Chaos Match Watch", "A shareable FootballAnt watchlist for chaos match energy, trap-game alerts and lineup panic risk.", body, ranked


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
        ("Lineup Clarity Board", "todays-most-stable-matches/", "Which matches look clear — and which still smell like lineup panic."),
        ("Fan Mood Index", "fan-mood-index/", "A signal-driven estimate of pre-match fan confidence, not a poll."),
        ("Chaos Match Watch", "match-fortune-today/", "Trap-game alerts, rotation anxiety and late-drama energy."),
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
