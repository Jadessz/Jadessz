#!/usr/bin/env python3
"""Render an animated contribution heatmap SVG for the profile README."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request

USER = sys.argv[1] if len(sys.argv) > 1 else "Jadessz"
OUT = sys.argv[2] if len(sys.argv) > 2 else "contrib-heatmap.svg"

CELL, GAP, RAD, LEFT, TOP = 13, 3, 3, 34, 24
# Soft neon greens on dark empty cells (readable on GitHub dark/light)
COLORS = ["#21262d", "#0d4429", "#006d32", "#26a641", "#39d353"]
GRAY = "#8b949e"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load_contributions(user: str) -> tuple[list[dict], int]:
    url = f"https://github-contributions-api.jogruber.de/v4/{user}?y=last"
    try:
        with urllib.request.urlopen(url, timeout=25) as resp:
            payload = json.loads(resp.read().decode())
        return payload["contributions"], int(payload["total"]["lastYear"])
    except Exception as exc:
        local = os.path.join(os.path.dirname(__file__), "..", "data", "contributions.json")
        if not os.path.exists(local):
            raise RuntimeError(f"API failed ({exc}) and no local snapshot at {local}") from exc
        print(f"API failed ({exc}); using {local}")
        with open(local, encoding="utf-8") as f:
            snapshot = json.load(f)
        days = snapshot["days"]
        # Map count -> approximate GitHub level when regenerating offline
        contribs = []
        for day in days:
            count = day["count"]
            if count == 0:
                level = 0
            elif count < 3:
                level = 1
            elif count < 6:
                level = 2
            elif count < 10:
                level = 3
            else:
                level = 4
            contribs.append({"date": day["date"], "count": count, "level": level})
        return contribs, int(snapshot["total_contributions"])


def edge_fade(week: int, week_count: int) -> float:
    """Gently fade the newest ~6 weeks so the grid softens on the right."""
    fade_weeks = 6
    from_end = week_count - 1 - week
    if from_end >= fade_weeks:
        return 1.0
    return 0.35 + 0.65 * (from_end / fade_weeks)


def main() -> None:
    contribs, total = load_contributions(USER)
    n = len(contribs)
    week_count = (n + 6) // 7
    width = LEFT + week_count * (CELL + GAP) + 6
    height = TOP + 7 * (CELL + GAP) + 28

    reveal, duration = 3.8, 0.55
    max_order = (week_count - 1) + 6 * 0.55

    labels: list[str] = []
    start = dt.date.fromisoformat(contribs[0]["date"])
    last_month = None
    for week in range(week_count):
        day = start + dt.timedelta(days=week * 7)
        if day.month != last_month:
            last_month = day.month
            x = LEFT + week * (CELL + GAP)
            labels.append(f'<text class="lbl" x="{x}" y="{TOP - 8}">{MONTHS[day.month - 1]}</text>')

    for name, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        y = TOP + row * (CELL + GAP) + CELL - 2
        labels.append(f'<text class="lbl" x="2" y="{y}">{name}</text>')

    rects: list[str] = []
    for i, cell in enumerate(contribs):
        week, row, level = i // 7, i % 7, int(cell["level"])
        x = LEFT + week * (CELL + GAP)
        y = TOP + row * (CELL + GAP)
        delay = round((week + row * 0.55) / max_order * reveal, 3)
        opacity = round(edge_fade(week, week_count), 3)
        cls = "c g" if level >= 1 else "c e"
        rects.append(
            f'<rect class="{cls}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
            f'rx="{RAD}" fill="{COLORS[level]}" style="animation-delay:{delay}s;'
            f'--end-opacity:{opacity}"/>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{USER}'s GitHub contribution graph" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">
<style>
  text.lbl {{ fill:{GRAY}; font-size:11px; font-weight:600; }}
  text.total {{ fill:#e6edf3; font-size:14px; font-weight:700; }}
  .c {{
    transform-box: fill-box;
    transform-origin: center;
    opacity: 0;
    animation: pop {duration}s ease-out both;
  }}
  .g {{
    animation: pop {duration}s ease-out both, flash {duration + 0.15:.2f}s ease-out both;
  }}
  @keyframes pop {{
    0% {{ opacity: 0; transform: scale(0.2); }}
    60% {{ opacity: var(--end-opacity, 1); transform: scale(1.12); }}
    100% {{ opacity: var(--end-opacity, 1); transform: scale(1); }}
  }}
  @keyframes flash {{
    0% {{ filter: brightness(2.3); }}
    40% {{ filter: brightness(2.3); }}
    100% {{ filter: brightness(1); }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    .c {{ opacity: var(--end-opacity, 1) !important; animation: none !important; }}
  }}
</style>
<rect width="{width}" height="{height}" fill="none"/>
{"".join(labels)}
{"".join(rects)}
<text class="total" x="{LEFT}" y="{height - 8}">{total:,} public contributions in the last year</text>
</svg>
"""

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Wrote {OUT}: {n} days, {total:,} contributions")


if __name__ == "__main__":
    main()
