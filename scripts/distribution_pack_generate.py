#!/usr/bin/env python3
"""Generate a review-only FootballAnt daily traffic operations pack.

This does not post externally. It extracts live/static FootballAnt signal surfaces and
creates draft social posts, comments, Telegram copy, short-video prompts, and share cards.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

SITE = "https://www.footballant.com/match-news"
BIG_MATCH_TERMS = [
    "Arsenal", "Chelsea", "Liverpool", "Manchester", "Tottenham", "West Ham", "Newcastle",
    "Real Madrid", "Barcelona", "Atletico", "Bayern", "Dortmund", "Paris Saint-Germain",
    "PSG", "Inter Milan", "AC Milan", "Juventus", "Roma", "Lazio", "Napoli", "Benfica",
    "Sporting CP", "Porto", "Celtic", "Rangers",
]


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def short_title(title: str) -> str:
    title = clean(title)
    title = re.sub(r"\s+(lineups|predicted lineup|predicted XI).*", "", title, flags=re.I)
    return title[:92]


def public_pick(rows: list[dict], fallback_idx: int = 0) -> dict:
    for row in rows:
        title = row.get("Match", "")
        if any(term.lower() in title.lower() for term in BIG_MATCH_TERMS):
            return row
    return rows[fallback_idx] if rows else {}


def extract_table(path: Path, limit: int = 12) -> list[dict]:
    soup = BeautifulSoup(path.read_text(errors="ignore"), "html.parser")
    rows: list[dict] = []
    table = soup.find("table")
    if not table:
        return rows
    headers = [clean(th.get_text(" ")) for th in table.find_all("th")]
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        vals = [clean(td.get_text(" ")) for td in cells]
        item = {headers[i] if i < len(headers) else f"col{i}": vals[i] for i in range(len(vals))}
        link = tr.find("a", href=True)
        if link:
            item["url"] = link["href"] if link["href"].startswith("http") else SITE.rstrip("/") + "/" + link["href"].lstrip("/")
        rows.append(item)
        if len(rows) >= limit:
            break
    return rows


def extract_chaos(path: Path, limit: int = 12) -> list[dict]:
    soup = BeautifulSoup(path.read_text(errors="ignore"), "html.parser")
    text_lines = [clean(x) for x in soup.get_text("\n").splitlines() if clean(x)]
    rows = []
    for i, line in enumerate(text_lines):
        if "Chaos read:" in line and i > 0:
            rows.append({"Match": text_lines[i - 1], "Chaos": line, "url": f"{SITE}/match-fortune-today/"})
        if len(rows) >= limit:
            break
    return rows


def find_font(size: int, bold: bool = False):
    names = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
    ]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            pass
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def card(path: Path, title: str, subtitle: str, rows: list[str], accent=(66, 214, 164)):
    W, H = 1200, 675
    img = Image.new("RGB", (W, H), (8, 16, 28))
    draw = ImageDraw.Draw(img)
    # simple gradient blocks
    for y in range(H):
        r = 8 + int(y / H * 12)
        g = 16 + int(y / H * 18)
        b = 28 + int(y / H * 24)
        draw.line((0, y, W, y), fill=(r, g, b))
    draw.rounded_rectangle((54, 48, W - 54, H - 48), 32, outline=(38, 61, 86), width=2, fill=(13, 25, 42))
    draw.text((86, 78), "FootballAnt Signals", fill=accent, font=find_font(28, True))
    draw.text((86, 128), title, fill=(245, 248, 252), font=find_font(54, True))
    y = 202
    for line in wrap(draw, subtitle, find_font(28), 980)[:2]:
        draw.text((86, y), line, fill=(177, 191, 210), font=find_font(28))
        y += 36
    y += 18
    for i, row in enumerate(rows[:5], 1):
        draw.rounded_rectangle((86, y, W - 86, y + 58), 18, fill=(20, 38, 62), outline=(44, 72, 102))
        draw.text((112, y + 14), f"{i}", fill=accent, font=find_font(26, True))
        draw.text((160, y + 13), row[:78], fill=(242, 246, 251), font=find_font(25, True))
        y += 72
    draw.text((86, H - 92), SITE + "/", fill=(142, 160, 184), font=find_font(24))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def build_pack(root: Path, out: Path) -> None:
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d")
    stable = extract_table(root / "todays-most-stable-matches/index.html", 10)
    mood = extract_table(root / "fan-mood-index/index.html", 10)
    chaos = extract_chaos(root / "match-fortune-today/index.html", 10)

    out.mkdir(parents=True, exist_ok=True)
    cards = out / "cards"
    card(cards / "lineup-clarity.png", "Lineup Clarity Board", "Who looks clear — and who still smells like lineup panic?", [short_title(x.get("Match", "")) + f" · {x.get('Read','')}" for x in stable])
    card(cards / "fan-mood-index.png", "Fan Mood Index", "Pre-match confidence, pressure and panic — signal-based, not a poll.", [short_title(x.get("Match", "")) + f" · {x.get('Social read','')}" for x in mood], accent=(255, 197, 92))
    card(cards / "chaos-match-watch.png", "Chaos Match Watch", "Trap-game alerts, rotation anxiety and late-drama energy.", [short_title(x.get("Match", "")) for x in chaos], accent=(143, 123, 255))

    hero = public_pick(mood) or (stable[0] if stable else {})
    clarity_item = public_pick(stable)
    chaos_item = public_pick(chaos)
    hero_match = short_title(hero.get("Match", "Liverpool vs Chelsea"))
    clarity_match = short_title(clarity_item.get("Match", "today’s least messy lineup read")) if clarity_item else "today’s least messy lineup read"
    clarity_read = clarity_item.get("Read", "Watch late team news") if clarity_item else "Watch late team news"
    chaos_match = short_title(chaos_item.get("Match", "today’s chaos watch")) if chaos_item else "today’s chaos watch"
    chaos_read = chaos_item.get("Chaos", "Chaos read") if chaos_item else "Chaos read"
    hero_mood = hero.get("Social read", hero.get("Mood", "Nervous confidence"))

    x_posts = [
        f"{hero_match}: {hero_mood}.\n\nThat’s the read. Not a fake fan poll — a signal-driven mood check from injuries, attention and lineup uncertainty.\n\n{SITE}/fan-mood-index/",
        f"I don’t trust a match until the XI is clear.\n\nToday’s least messy lineup read: {clarity_match}\nSignal: {clarity_read}\n\nLineup clarity board: {SITE}/todays-most-stable-matches/",
        f"Some games don’t need another 2-1 prediction. They need a panic meter.\n\nRotation risk. Injury tension. Late team-news chaos.\n\nFootballAnt Match Signals: {SITE}/",
        f"Chaos Match Watch is live.\n\nFirst game that smells unstable: {chaos_match}\n{chaos_read}\n\nThis is the pre-match layer most prediction pages skip.\n{SITE}/match-fortune-today/",
        "Football internet has enough score predictions.\n\nWe’re more interested in the weird stuff before kickoff:\n- lineup panic\n- trap-game energy\n- injury tension\n- fans pretending to be calm\n\n" + SITE + "/",
    ]

    comments = [
        "I don’t trust this one until the XI is clearer. Feels like a lineup panic game, not a clean prediction game.",
        "This has trap-game smell. Not because of the scoreline — because the pre-match signals look messy.",
        "Fans are pretending to be calm here. The lineup uncertainty says otherwise.",
        "This is exactly the kind of match where a normal prediction ages badly after team news drops.",
        "Rotation roulette tonight. I’d wait for the XI before sounding confident.",
        "Feels less like ‘who wins?’ and more like ‘how chaotic does this get?’",
        "The injury tension is the story here. Score predictions are secondary until availability is clearer.",
        "Nobody needs another confident 2-1 take. This one needs a panic meter.",
    ]

    telegram = [
        f"⚽ FootballAnt Signals\n\nLineup Clarity Board is live.\nLeast messy read: {clarity_match}\nSignal: {clarity_read}\n\nUseful before kickoff because team news ruins lazy predictions.\n{SITE}/todays-most-stable-matches/",
        f"📊 Fan Mood Index\n\n{hero_match}: {hero_mood}\nInjury tension: {hero.get('Injury Tension', hero.get('Injury Pressure','Medium'))}\n\nSignal-based mood proxy, not a fan poll.\n{SITE}/fan-mood-index/",
        f"🌪 Chaos Match Watch\n\nToday’s first trap-game smell: {chaos_match}\n{chaos_read}\n\nRotation anxiety, injury tension and late-drama energy in one board.\n{SITE}/match-fortune-today/",
    ]

    reddit_prompts = [
        f"For {hero_match}, would you trust the predicted XI yet, or is availability still the main swing factor?",
        "What do you trust more before kickoff: score predictions or lineup clarity?",
        "Which match today has the strongest chaos/trap-game energy because of rotation or injuries?",
        f"{clarity_match} looks like one of the less messy lineup reads today. Fans of either side: fair or completely wrong?",
        "Question for club fans: what is the earliest source you actually trust for lineup/injury confidence before the official XI drops?",
    ]

    shorts = [
        f"Hook: One match today actually looks readable.\nVisual: Lineup Clarity card.\nScript: 'Before kickoff, most predictions are guessing. {clarity_match} looks like one of today’s less messy lineup reads — {clarity_read.lower()}, not blind confidence.'",
        f"Hook: Fans are pretending to be calm.\nVisual: Fan Mood card.\nScript: '{hero_match}: {hero_mood.lower()}. That is not a fan poll — it is a signal read from injuries, attention and lineup pressure.'",
        f"Hook: This one smells chaotic.\nVisual: Chaos Watch card.\nScript: '{chaos_match} has trap-game energy: rotation anxiety, injury tension and late team-news chaos. This is the stuff score predictions usually hide.'",
    ]

    index = {
        "date": today,
        "generated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        "source_root": str(root),
        "policy": "review-only; do not post externally without approval; no fake fan polls, no betting advice, no invented sources",
        "links": {
            "lineup_clarity": f"{SITE}/todays-most-stable-matches/",
            "mood": f"{SITE}/fan-mood-index/",
            "chaos": f"{SITE}/match-fortune-today/",
        },
        "top_items": {"lineup_clarity": stable[:5], "mood": mood[:5], "chaos": chaos[:5]},
        "x_posts": x_posts,
        "comments": comments,
        "telegram": telegram,
        "reddit_prompts": reddit_prompts,
        "short_video_scripts": shorts,
        "cards": [str(p.relative_to(out)) for p in sorted(cards.glob("*.png"))],
    }
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2))

    def md_list(title: str, items: Iterable[str]) -> str:
        return "\n## " + title + "\n\n" + "\n\n---\n\n".join(items) + "\n"

    md = f"# FootballAnt Traffic Ops Pack — {today}\n\nReview-only. Nothing here has been posted externally.\n"
    md += md_list("X posts", x_posts)
    md += md_list("X/Reddit comment candidates", comments)
    md += md_list("Telegram posts", telegram)
    md += md_list("Reddit-safe discussion prompts", reddit_prompts)
    md += md_list("Short video scripts", shorts)
    md += "\n## Cards\n\n" + "\n".join(f"- `{c}`" for c in index["cards"]) + "\n"
    (out / "traffic_ops_pack.md").write_text(md)

    # separate platform files
    (out / "x_posts.md").write_text(md_list("X posts", x_posts).strip() + "\n")
    (out / "comments.md").write_text(md_list("Comment candidates", comments).strip() + "\n")
    (out / "telegram_posts.md").write_text(md_list("Telegram posts", telegram).strip() + "\n")
    (out / "reddit_prompts.md").write_text(md_list("Reddit-safe discussion prompts", reddit_prompts).strip() + "\n")
    (out / "short_video_scripts.md").write_text(md_list("Short video scripts", shorts).strip() + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/aboo/footballant/match-news-publish")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    out = Path(args.out) if args.out else Path("/Users/aboo/footballant/7-day-first-google-click/state/distribution") / now.strftime("%Y-%m-%d")
    build_pack(Path(args.root), out)
    print(f"Wrote distribution pack: {out}")


if __name__ == "__main__":
    main()
