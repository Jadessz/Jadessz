#!/usr/bin/env python3
"""Render stats, top-languages and streak cards that include private repos.

Stats and languages need a token that can read private repos (GH_STATS_TOKEN).
Only aggregate numbers and language names are rendered, never repo names.
The streak card reads data/contributions.json and needs no token.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys

import requests

ROOT = os.path.join(os.path.dirname(__file__), "..")
TOKEN = os.environ.get("GH_STATS_TOKEN", "")
API = "https://api.github.com/graphql"

# tokyonight, matching the cards these replace
BG, TITLE, TEXT, ICON, MUTED = "#1a1b27", "#70a5fd", "#38bdae", "#bf91f3", "#a9b1d6"
FONT = "'Segoe UI',Ubuntu,'Helvetica Neue',Sans-Serif"


def gql(query: str, variables: dict | None = None) -> dict:
    resp = requests.post(
        API,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"bearer {TOKEN}"},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def fetch_stats() -> dict:
    base = gql(
        """{
          viewer {
            login
            contributionsCollection { contributionYears }
            pullRequests { totalCount }
            issues { totalCount }
            repositoriesContributedTo(includeUserRepositories: true,
              contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) { totalCount }
          }
        }"""
    )["viewer"]

    commits = reviews = contributions = private = 0
    for year in base["contributionsCollection"]["contributionYears"]:
        c = gql(
            """query($from: DateTime!, $to: DateTime!) {
              viewer { contributionsCollection(from: $from, to: $to) {
                totalCommitContributions
                totalPullRequestReviewContributions
                restrictedContributionsCount
                contributionCalendar { totalContributions }
              } }
            }""",
            {"from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"},
        )["viewer"]["contributionsCollection"]
        commits += c["totalCommitContributions"]
        reviews += c["totalPullRequestReviewContributions"]
        contributions += c["contributionCalendar"]["totalContributions"]
        # Contributions in private repos the token can't open (e.g. employer repos)
        private += c["restrictedContributionsCount"]

    stars = 0
    languages: dict[str, dict] = {}
    cursor = None
    while True:
        page = gql(
            """query($after: String) {
              viewer { repositories(first: 100, after: $after, isFork: false,
                ownerAffiliations: [OWNER, ORGANIZATION_MEMBER, COLLABORATOR]) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  stargazerCount
                  languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
                    edges { size node { name color } }
                  }
                }
              } }
            }""",
            {"after": cursor},
        )["viewer"]["repositories"]
        for repo in page["nodes"]:
            stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                lang = languages.setdefault(
                    edge["node"]["name"], {"size": 0, "color": edge["node"]["color"] or MUTED}
                )
                lang["size"] += edge["size"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    return {
        "login": base["login"],
        "commits": commits,
        "reviews": reviews,
        "contributions": contributions,
        "private": private,
        "prs": base["pullRequests"]["totalCount"],
        "issues": base["issues"]["totalCount"],
        "repos": base["repositoriesContributedTo"]["totalCount"],
        "stars": stars,
        "languages": languages,
    }


def card(width: int, height: int, title: str, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}" font-family="{FONT}">
<style>
  .t {{ fill:{TITLE}; font-size:18px; font-weight:600; }}
  .l {{ fill:{TEXT}; font-size:14px; font-weight:600; }}
  .v {{ fill:{TEXT}; font-size:14px; font-weight:700; }}
  .m {{ fill:{MUTED}; font-size:11px; }}
  .f {{ opacity:0; animation: fade .5s ease-out forwards; }}
  @keyframes fade {{ to {{ opacity:1; }} }}
  @media (prefers-reduced-motion: reduce) {{ .f {{ opacity:1; animation:none; }} }}
</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="4.5" fill="{BG}"/>
<text class="t" x="25" y="35">{html.escape(title)}</text>
{body}
</svg>
"""


def stats_card(s: dict) -> str:
    rows = [
        ("Total Commits", s["commits"]),
        ("Private Contributions", s["private"]),
        ("Pull Requests", s["prs"]),
        ("Code Reviews", s["reviews"]),
        ("Issues", s["issues"]),
        ("Repos Contributed To", s["repos"]),
        ("Total Stars", s["stars"]),
    ]
    body = []
    for i, (label, value) in enumerate(rows):
        y = 64 + i * 25
        delay = 0.15 * (i + 1)
        body.append(
            f'<g class="f" style="animation-delay:{delay:.2f}s">'
            f'<circle cx="31" cy="{y - 5}" r="4" fill="{ICON}"/>'
            f'<text class="l" x="45" y="{y}">{label}:</text>'
            f'<text class="v" x="245" y="{y}">{value:,}</text></g>'
        )
    cx, cy, r = 390, 122, 48
    body.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{TITLE}" stroke-opacity=".2" stroke-width="6"/>'
        f'<circle class="f" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{TITLE}" stroke-width="6"/>'
        f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" fill="{TEXT}" font-size="20" font-weight="800">'
        f'{s["contributions"]:,}</text>'
        f'<text class="m" x="{cx}" y="{cy + 20}" text-anchor="middle">contributions</text>'
        f'<text class="m" x="25" y="{64 + len(rows) * 25 + 2}">incl. private repos · all time</text>'
    )
    return card(495, 255,f"{s['login']}'s GitHub Stats", "".join(body))


def langs_card(languages: dict, limit: int = 8) -> str:
    ranked = sorted(languages.items(), key=lambda kv: kv[1]["size"], reverse=True)[:limit]
    total = sum(v["size"] for _, v in ranked) or 1
    width, bar_w = 300, 250

    body = [f'<mask id="bar"><rect x="25" y="52" width="{bar_w}" height="8" rx="4" fill="#fff"/></mask>']
    x = 25.0
    segs = []
    for name, v in ranked:
        w = bar_w * v["size"] / total
        segs.append(f'<rect x="{x:.2f}" y="52" width="{w:.2f}" height="8" fill="{v["color"]}"/>')
        x += w
    body.append(f'<g mask="url(#bar)">{"".join(segs)}</g>')

    for i, (name, v) in enumerate(ranked):
        col, row = i % 2, i // 2
        lx, ly = 25 + col * 135, 84 + row * 22
        pct = 100 * v["size"] / total
        body.append(
            f'<g class="f" style="animation-delay:{0.1 * (i + 1):.2f}s">'
            f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{v["color"]}"/>'
            f'<text x="{lx + 15}" y="{ly}" fill="{TEXT}" font-size="11">'
            f'{html.escape(name)} {pct:.1f}%</text></g>'
        )
    height = 84 + ((len(ranked) + 1) // 2) * 22 + 4
    return card(width, max(height, 165), "Most Used Languages", "".join(body))


def streak_card(data: dict) -> str:
    def fmt(date: str | None) -> str:
        if not date:
            return "—"
        d = dt.date.fromisoformat(date)
        return f"{d:%b} {d.day}"

    cur, best = data["current_streak"], data["longest_streak"]
    cols = [
        (82, f"{data['total_contributions']:,}", "Contributions",
         f"{fmt(data['range']['start'])} – Present"),
        (247, str(cur["length"]), "Current Streak", f"{fmt(cur['start'])} – {fmt(cur['end'])}"),
        (412, str(best["length"]), "Longest Streak", f"{fmt(best['start'])} – {fmt(best['end'])}"),
    ]
    body = [
        f'<line x1="165" y1="58" x2="165" y2="170" stroke="{MUTED}" stroke-opacity=".3"/>'
        f'<line x1="330" y1="58" x2="330" y2="170" stroke="{MUTED}" stroke-opacity=".3"/>'
    ]
    for i, (x, value, label, sub) in enumerate(cols):
        color = ICON if i == 1 else TEXT
        body.append(
            f'<g class="f" style="animation-delay:{0.2 * (i + 1):.2f}s" text-anchor="middle">'
            f'<text x="{x}" y="105" fill="{color}" font-size="28" font-weight="700">{value}</text>'
            f'<text x="{x}" y="135" fill="{TITLE}" font-size="14" font-weight="600">{label}</text>'
            f'<text class="m" x="{x}" y="157">{sub}</text></g>'
        )
    return card(495, 195, "Contribution Streak · last year", "".join(body))


def write(path: str, svg: str) -> None:
    with open(os.path.join(ROOT, path), "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {path}")


if __name__ == "__main__":
    with open(os.path.join(ROOT, "data", "contributions.json"), encoding="utf-8") as f:
        write("streak-card.svg", streak_card(json.load(f)))

    if not TOKEN:
        print("GH_STATS_TOKEN not set; skipping stats and languages cards", file=sys.stderr)
        sys.exit(0)

    stats = fetch_stats()
    write("stats-card.svg", stats_card(stats))
    write("top-langs-card.svg", langs_card(stats["languages"]))
