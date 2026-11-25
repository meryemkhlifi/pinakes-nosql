"""Day 5 integration check: the five demo scenarios of the plan, through the API.

Start every service first (docker compose ... up -d for both stacks, then
`uvicorn backend.app.main:app --port 8000`), then from the repo root:
    python scripts/check_day5_demo.py
    python scripts/check_day5_demo.py --expect-alerts     # after running the bot (scenario 5)
    python scripts/check_day5_demo.py --ui                # also check that Streamlit answers
Each scenario prints [OK] or [FAIL] lines. Exit code 0 when everything is [OK].
It writes 3 views and 1 read event (user u_demo_check) to prove the counters move.
"""

import argparse
import sys
import time
from collections.abc import Callable

import httpx

API = "http://localhost:8000"
STREAMLIT = "http://localhost:8501"


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def check(self, ok: bool, text: str) -> bool:
        print(("[OK]   " if ok else "[FAIL] ") + text)
        if not ok:
            self.problems.append(text)
        return ok


def guarded(report: Report, name: str, fn: Callable[[], None]) -> None:
    """Run one scenario. A crash (service off, bad answer) is one [FAIL], not a stack trace."""
    print(f"\n== {name}")
    try:
        fn()
    except httpx.HTTPStatusError as exc:
        r = exc.response
        report.check(
            False,
            f"{r.request.method} {r.request.url.path} -> {r.status_code} {r.text[:100]}",
        )
    except httpx.HTTPError as exc:
        report.check(False, f"API not reachable ({exc.__class__.__name__}). Is uvicorn running?")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        report.check(False, f"unexpected answer ({exc.__class__.__name__}: {exc})")


def get(client: httpx.Client, path: str, **params) -> httpx.Response:
    r = client.get(path, params=params)
    r.raise_for_status()
    return r


def scenario_search(client: httpx.Client, report: Report) -> None:
    r = get(client, "/search", q="republc")  # a typo on purpose
    titles = [h["title"].lower() for h in r.json()["hits"]]
    report.check(
        any("republic" in t for t in titles),
        f"search 'republc' finds The Republic ({len(titles)} hits)",
    )
    report.check(
        "highlight" in str(r.json()["hits"]) or r.json()["total"] > 0,
        "search returns hits (highlights when the work has an incipit)",
    )
    report.check(bool(r.json()["facets"]["genre"]), "facets by genre are returned")
    first = get(client, "/search", q="republic", size=5)
    second = get(client, "/search", q="republic", size=5)
    report.check(
        second.headers.get("x-cache") == "HIT",
        "second identical search is served from Redis "
        f"(X-Cache: {first.headers.get('x-cache')} then {second.headers.get('x-cache')})",
    )
    genre = r.json()["facets"]["genre"][0]["key"]
    filtered = get(client, "/search", q="republic", genre=genre).json()["hits"]
    report.check(all(h["genre"] == genre for h in filtered), f"genre filter '{genre}' is applied")
    report.check(
        len(get(client, "/suggest", q="rep").json()) > 0,
        "/suggest?q=rep proposes titles",
    )


def scenario_graph(client: httpx.Client, report: Report) -> None:
    top = get(client, "/graph/influence/top", n=5).json()
    report.check(
        len(top) >= 1 and top[0]["score"] > 0,
        f"PageRank top: {[t['name'] for t in top]}",
    )
    center = top[0]["author_id"]
    nb = get(client, f"/graph/neighbors/{center}", depth=1).json()
    report.check(bool(nb["edges"]), f"{top[0]['name']} has {len(nb['edges'])} direct link(s)")
    if not nb["edges"]:
        return
    edge = nb["edges"][0]
    other = edge["target"] if edge["source"] == center else edge["source"]
    path = get(client, "/graph/path", **{"from": center, "to": other}).json()
    report.check(
        path["found"] and path["length"] == 1,
        f"path {center} <-> {other}: length {path['length']}",
    )
    missing = client.get("/graph/path", params={"from": center, "to": "a_does_not_exist"})
    report.check(missing.status_code == 404, "unknown author gives 404")


def pick_work(client: httpx.Client) -> tuple[str, str]:
    genres = get(client, "/catalog/genres").json()
    authors = get(client, f"/catalog/genres/{genres[0]['genre']}/authors").json()
    work = authors[0]["works"][0]
    return work["id"], work["title"]


def scenario_browse(client: httpx.Client, report: Report) -> None:
    genres = get(client, "/catalog/genres").json()
    report.check(len(genres) >= 5, f"{len(genres)} genres in MongoDB")
    authors = get(client, f"/catalog/genres/{genres[0]['genre']}/authors").json()
    report.check(bool(authors), f"genre '{genres[0]['genre']}' has {len(authors)} author(s)")
    work_id, title = pick_work(client)
    report.check(
        get(client, f"/catalog/works/{work_id}").json()["title"] == title,
        f"work {work_id} '{title}' opens",
    )


def views_of(client: httpx.Client, work_id: str) -> int:
    rows = get(client, "/popular", n=100).json()
    return next((r["views"] for r in rows if r["id"] == work_id), 0)


def scenario_popular(client: httpx.Client, report: Report) -> None:
    work_id, _ = pick_work(client)
    before = views_of(client, work_id)
    for _ in range(3):
        get(client, f"/catalog/works/{work_id}")
    after = views_of(client, work_id)
    report.check(
        after == before + 3,
        f"'most read' counter of {work_id}: {before} -> {after} (+3 expected)",
    )


def reads_today(client: httpx.Client, work_id: str) -> int:
    return get(client, f"/events/work/{work_id}").json()["count"]


def scenario_events_and_monitoring(
    client: httpx.Client, report: Report, expect_alerts: bool
) -> None:
    work_id = "w_0003"  # fixed: this scenario must work with stack B alone
    before = reads_today(client, work_id)
    r = client.post("/events/read", json={"work_id": work_id, "user_id": "u_demo_check"})
    report.check(r.status_code == 201, f"POST /events/read -> {r.status_code}")
    after = reads_today(client, work_id)
    report.check(
        after == before + 1,
        f"reads of {work_id} today (Cassandra): {before} -> {after} (+1 expected)",
    )
    history = get(client, "/events/user/u_demo_check").json()
    report.check(
        any(h["work_id"] == work_id for h in history),
        "the read appears in the history of the user",
    )
    alerts = get(client, "/monitoring/alerts", limit=5).json()
    report.check(isinstance(alerts, list), f"/monitoring/alerts answers ({len(alerts)} alert(s))")
    if expect_alerts:
        report.check(
            any(a["z_score"] > 3 for a in alerts),
            "an alert with z > 3 exists "
            "(run scripts/zscore_alert.py and scripts/bot_simulator.py first)",
        )


def check_streamlit(report: Report) -> None:
    try:
        r = httpx.get(f"{STREAMLIT}/_stcore/health", timeout=5)
        report.check(
            r.status_code == 200 and r.text.strip() == "ok",
            f"Streamlit answers on {STREAMLIT}",
        )
    except httpx.HTTPError:
        report.check(
            False,
            f"Streamlit not reachable on {STREAMLIT} (streamlit run frontend/Home.py)",
        )


def run(client: httpx.Client, expect_alerts: bool = False, ui: bool = False) -> Report:
    report = Report()
    guarded(
        report,
        "1. Search with a typo, filters, highlights (Elasticsearch, Redis)",
        lambda: scenario_search(client, report),
    )
    guarded(
        report,
        "2. Graph: path and PageRank (Neo4j)",
        lambda: scenario_graph(client, report),
    )
    guarded(
        report,
        "3. Browse genre > author > works (MongoDB)",
        lambda: scenario_browse(client, report),
    )
    guarded(
        report,
        "4. 'Most read' moves when works are opened (Redis)",
        lambda: scenario_popular(client, report),
    )
    guarded(
        report,
        "5. Reads per day and alerts (Cassandra, ELK)",
        lambda: scenario_events_and_monitoring(client, report, expect_alerts),
    )
    if ui:
        print("\n== Web interface")
        check_streamlit(report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=API)
    ap.add_argument("--expect-alerts", action="store_true")
    ap.add_argument("--ui", action="store_true")
    args = ap.parse_args()
    started = time.time()
    with httpx.Client(base_url=args.api, timeout=20) as client:
        report = run(client, args.expect_alerts, args.ui)
    print(f"\n{len(report.problems)} problem(s) in {time.time() - started:.1f} s")
    sys.exit(1 if report.problems else 0)


if __name__ == "__main__":
    main()
