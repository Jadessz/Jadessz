#!/usr/bin/env python3
"""Scrape public contribution counts from GitHub (no auth required)."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

USERNAME = os.environ.get("GH_PROFILE_USER", "Jadessz")
URL = f"https://github.com/users/{USERNAME}/contributions"
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "contributions.json")


def fetch_days() -> list[dict]:
    resp = requests.get(
        URL,
        headers={"User-Agent": "jadessz-profile-readme/1.0"},
        timeout=30,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    cells = soup.select("td.ContributionCalendar-day")
    if not cells:
        print("no calendar cells found — GitHub markup may have changed", file=sys.stderr)
        sys.exit(1)

    days = []
    for td in cells:
        date = td.get("data-date")
        if not date:
            continue
        td_id = td.get("id")
        tip = soup.find("tool-tip", attrs={"for": td_id}) if td_id else None
        text = tip.get_text(strip=True) if tip else ""
        if re.search(r"no contributions", text, re.I):
            count = 0
        else:
            match = re.match(r"(\d+)", text)
            count = int(match.group(1)) if match else int(td.get("data-level") or 0)
        days.append({"date": date, "count": count})

    days.sort(key=lambda d: d["date"])
    return days


def streak_current(days: list[dict]) -> tuple[int, str | None, str | None]:
    idx = len(days) - 1
    if days[idx]["count"] == 0:
        idx -= 1
    length = 0
    end_idx = idx
    while idx >= 0 and days[idx]["count"] > 0:
        length += 1
        idx -= 1
    if length == 0:
        return 0, None, None
    start_idx = idx + 1
    return length, days[start_idx]["date"], days[end_idx]["date"]


def streak_longest(days: list[dict]) -> tuple[int, str | None, str | None]:
    longest = run = 0
    longest_start = longest_end = None
    run_start = None
    for i, day in enumerate(days):
        if day["count"] > 0:
            if run == 0:
                run_start = i
            run += 1
            if run > longest:
                longest = run
                longest_start = days[run_start]["date"]
                longest_end = day["date"]
        else:
            run = 0
    return longest, longest_start, longest_end


def build_payload(days: list[dict]) -> dict:
    total = sum(d["count"] for d in days)
    active = sum(1 for d in days if d["count"] > 0)
    best = max(days, key=lambda d: d["count"])
    cur_len, cur_start, cur_end = streak_current(days)
    long_len, long_start, long_end = streak_longest(days)

    return {
        "username": USERNAME,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "range": {"start": days[0]["date"], "end": days[-1]["date"]},
        "total_contributions": total,
        "active_days": active,
        "current_streak": {"length": cur_len, "start": cur_start, "end": cur_end},
        "longest_streak": {"length": long_len, "start": long_start, "end": long_end},
        "best_day": {"date": best["date"], "count": best["count"]},
        "days": days,
    }


if __name__ == "__main__":
    days = fetch_days()
    data = build_payload(days)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(
        f"wrote {OUT_PATH}: {data['total_contributions']} contributions, "
        f"current streak {data['current_streak']['length']}"
    )
