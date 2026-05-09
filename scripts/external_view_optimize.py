#!/usr/bin/env python3
"""Add attributed external-view sections to FootballAnt match pages.

The goal is to increase editorial/information-gain signals without copying or
pretending third-party opinions are FootballAnt originals. We only use public
source metadata already collected by the pipeline: source, title/summary, URL.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

SECTION_RE = re.compile(r'\s*<section class="external-view-section">.*?</section>', re.S)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def clean(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def collect_tracking(*states: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for state in states:
        tracking = state.get("news_update_tracking") if isinstance(state, dict) else None
        if not isinstance(tracking, dict):
            triggered = state.get("triggered") if isinstance(state, dict) else None
            tracking = {}
            if isinstance(triggered, list):
                for entry in triggered:
                    if isinstance(entry, dict) and entry.get("match_id"):
                        tracking[str(entry.get("match_id"))] = entry
        for match_id, record in tracking.items():
            if not isinstance(record, dict):
                continue
            items = record.get("items") or record.get("news") or record.get("updates") or []
            if not isinstance(items, list):
                continue
            clean_items = []
            seen = set()
            for item in items:
                if not isinstance(item, dict):
                    continue
                source = clean(item.get("source") or item.get("name") or item.get("publisher"))
                title = clean(item.get("title"))
                summary = clean(item.get("summary") or item.get("description"))
                url = clean(item.get("url"))
                if not source or not (title or summary) or not url:
                    continue
                key = (source.lower(), title.lower(), url)
                if key in seen:
                    continue
                seen.add(key)
                clean_items.append({"source": source, "title": title or summary, "summary": summary, "url": url})
            if clean_items:
                out[str(match_id)] = clean_items[:4]
    return out


def match_id_from_page(text: str) -> str | None:
    m = re.search(r'https://www\.footballant\.com/matches/(\d+)', text)
    return m.group(1) if m else None


def external_view_section(items: list[dict[str, str]]) -> str:
    rows = []
    for item in items[:3]:
        title = item["title"]
        summary = item.get("summary") or ""
        title_l = title.lower().rstrip(" .")
        summary_l = summary.lower().rstrip(" .")
        if summary and summary_l != title_l and title_l not in summary_l:
            note = f"{title} — {summary}"
        else:
            note = title
        note = note[:260].rstrip(" .") + ("…" if len(note) > 260 else "")
        rows.append(
            f'              <li><a href="{esc(item["url"])}">{esc(item["source"])}</a>: {esc(note)}</li>'
        )
    return "\n".join([
        '          <section class="external-view-section">',
        '            <h2>External view</h2>',
        '            <p>FootballAnt checks outside coverage before kickoff and treats these items as attributed context, not as confirmed lineup claims unless the source itself confirms the detail.</p>',
        '            <ul>',
        *rows,
        '            </ul>',
        '          </section>',
    ])


def patch_page(path: Path, tracking: dict[str, list[dict[str, str]]]) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    match_id = match_id_from_page(text)
    if not match_id or match_id not in tracking:
        return False
    section = external_view_section(tracking[match_id])
    stripped = SECTION_RE.sub("", text)
    if "<h2>Prediction</h2>" in stripped:
        new = re.sub(r'(\n\s*<section>\s*\n\s*<h2>Prediction</h2>)', "\n" + section + r"\1", stripped, count=1)
    elif "<h2>Tactical Notes</h2>" in stripped:
        new = re.sub(r'(\n\s*<section>\s*\n\s*<h2>Tactical Notes</h2>)', "\n" + section + r"\1", stripped, count=1)
    else:
        return False
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def optimize(root: Path, state_paths: list[Path]) -> dict[str, Any]:
    states = [load_json(path) for path in state_paths]
    tracking = collect_tracking(*states)
    patched = 0
    for path in (root / "matches").glob("*/index.html"):
        if patch_page(path, tracking):
            patched += 1
    return {"root": str(root), "tracking_matches": len(tracking), "pages_patched": patched}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--state", action="append", required=True)
    args = parser.parse_args()
    results = [optimize(Path(root), [Path(p) for p in args.state]) for root in args.root]
    print(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
