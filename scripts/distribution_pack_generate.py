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


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def short_title(title: str) -> str:
    title = clean(title)
    title = re.sub(r"\s+(lineups|predicted lineup|predicted XI).*", "", title, flags=re.I)
    return title[:92]


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


def extract_fortune(path: Path, limit: int = 12) -> list[dict]:
    soup = BeautifulSoup(path.read_text(errors="ignore"), "html.parser")
    text_lines = [clean(x) for x in soup.get_text("\n").splitlines() if clean(x)]
    rows = []
    for i, line in enumerate(text_lines):
        if "Match fortune:" in line and i > 0:
            rows.append({"Match": text_lines[i - 1], "Fortune": line, "url": f"{SITE}/match-fortune-today/"})
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
    fortune = extract_fortune(root / "match-fortune-today/index.html", 10)

    out.mkdir(parents=True, exist_ok=True)
    cards = out / "cards"
    card(cards / "stable-matches.png", "Today’s Most Stable Matches", "Low-drama lineup reads from FootballAnt Match Signals.", [short_title(x.get("Match", "")) + f" · {x.get('Stable Index','')}" for x in stable])
    card(cards / "fan-mood-index.png", "Fan Mood Index", "A football mood proxy based on source activity and match signals — not a fan poll.", [short_title(x.get("Match", "")) + f" · {x.get('Mood','')}" for x in mood], accent=(255, 197, 92))
    card(cards / "match-fortune.png", "Match Fortune Today", "A light football signal board for matches that feel stable, risky or chaotic.", [short_title(x.get("Match", "")) for x in fortune], accent=(143, 123, 255))

    hero = mood[0] if mood else stable[0]
    hero_match = short_title(hero.get("Match", "Liverpool vs Chelsea"))
    stable_match = short_title(stable[0].get("Match", "today’s most stable match")) if stable else "today’s most stable match"
    fortune_match = short_title(fortune[0].get("Match", "today’s chaos watch")) if fortune else "today’s chaos watch"

    x_posts = [
        f"{hero_match} has one of today’s stronger FootballAnt mood reads.\n\nMood: {hero.get('Mood','Confident')}\nMarket confidence: {hero.get('Market Confidence','High')}\nInjury pressure: {hero.get('Injury Pressure','Medium')}\n\nFull Fan Mood board: {SITE}/fan-mood-index/",
        f"Today’s low-drama board is live.\n\nMost stable signal: {stable_match}\n\nThis is based on lineup certainty, injury pressure and volatility watch — not betting advice.\n{SITE}/todays-most-stable-matches/",
        f"Some matches don’t need a bold score prediction. They need a risk label.\n\nFootballAnt Match Signals tracks rotation risk, injury pressure, market confidence and lineup certainty before kickoff.\n{SITE}/",
        f"Match Fortune Today is live: a lighter way to scan which fixtures feel stable, risky or chaotic.\n\nFirst watch: {fortune_match}\n{SITE}/match-fortune-today/",
        "Prediction pages are easy to copy. Signal boards are harder.\n\nFootballAnt is moving toward match intelligence: lineup certainty, injury pressure, market watch and fan mood in one place.\n" + SITE + "/",
    ]

    comments = [
        "The key here isn’t just the score prediction — it’s lineup certainty. If that stays low, I’d treat the whole match read as unstable.",
        "This has chaos-match energy: injury pressure plus uncertain rotation usually matters more than the headline prediction.",
        "I’d look less at the final score pick and more at whether the expected XI is actually stable. Late team news can flip this kind of match.",
        "Interesting matchup, but the risk signal is availability. If the injury pressure is medium/high, the prediction should stay cautious.",
        "This feels like one of those games where fan confidence and lineup certainty move in opposite directions. Fun, but risky to read early.",
        "For me the useful question is: stable match or chaos match? This one looks closer to chaos unless the XI gets clearer before kickoff.",
        "The match mood is confident, but I’d still watch rotation risk. A good-looking fixture can get messy fast when the lineup is uncertain.",
        "Not every preview needs another 2-1 prediction. The better signal is whether injuries, rotation and media attention are all pointing the same way.",
    ]

    telegram = [
        f"⚽ FootballAnt Signals\n\nToday’s Most Stable Matches is live.\nTop watch: {stable_match}\n\nUse it as a pre-match stability board, not a betting tip.\n{SITE}/todays-most-stable-matches/",
        f"📊 Fan Mood Index\n\nTop mood read: {hero_match}\nMood: {hero.get('Mood','Confident')}\nMarket confidence: {hero.get('Market Confidence','High')}\nInjury pressure: {hero.get('Injury Pressure','Medium')}\n\n{SITE}/fan-mood-index/",
        f"🔮 Match Fortune Today\n\nLightweight football signal board: stable, risky or chaotic match moods.\nWatch: {fortune_match}\n\n{SITE}/match-fortune-today/",
    ]

    reddit_prompts = [
        f"For {hero_match}, would you trust the predicted XI yet, or is availability still the main swing factor?",
        "Do you usually care more about score predictions or lineup certainty before kickoff? I’m starting to think lineup certainty is the cleaner signal.",
        "Which match today feels most likely to turn chaotic because of rotation/injury pressure rather than tactics?",
        f"{stable_match} looks relatively stable on pre-match signals. Fans of either side: does that match what you’re seeing?",
        "Question for club fans: what is the earliest source you trust for lineup/injury confidence before the official XI drops?",
    ]

    shorts = [
        f"Hook: One match today looks calmer than the rest.\nVisual: Stable Matches card.\nScript: 'Before kickoff, not every game is chaos. FootballAnt’s stability board flags {stable_match} as one of today’s cleaner reads based on lineup certainty, injury pressure and volatility watch.'",
        f"Hook: This match has fan mood energy.\nVisual: Fan Mood card.\nScript: '{hero_match}: mood looks {hero.get('Mood','confident').lower()}, but injury pressure still matters. This is why we track mood and risk separately.'",
        f"Hook: Match fortune says be careful.\nVisual: Fortune card.\nScript: '{fortune_match} gets a high-risk mood on FootballAnt. Not a betting tip — just a quick way to spot which fixtures feel messy before kickoff.'",
    ]

    index = {
        "date": today,
        "generated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        "source_root": str(root),
        "policy": "review-only; do not post externally without approval; no fake fan polls, no betting advice, no invented sources",
        "links": {
            "stable": f"{SITE}/todays-most-stable-matches/",
            "mood": f"{SITE}/fan-mood-index/",
            "fortune": f"{SITE}/match-fortune-today/",
        },
        "top_items": {"stable": stable[:5], "mood": mood[:5], "fortune": fortune[:5]},
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
