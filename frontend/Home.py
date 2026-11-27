import os

import httpx
import streamlit as st

import ui

API_URL = os.getenv("API_URL", "http://localhost:8000")

ui.setup(
    "home",
    "Pinakes 2.0",
    "A modern Pinakes: the catalog of the Library of Alexandria rebuilt on MongoDB, "
    "Elasticsearch, Redis, Neo4j, Cassandra and ELK.",
    eyebrow="Welcome",
)


def api_get(path: str, **params):
    r = httpx.get(f"{API_URL}{path}", params=params, timeout=5)
    r.raise_for_status()
    return r.json()


# ---- API health (same check as before) ----
try:
    r = httpx.get(f"{API_URL}/health", timeout=2)
    api_ok, api_message = True, f"API reachable at {API_URL} (status {r.status_code})"
except Exception:
    api_ok = False
    api_message = f"API not reachable at {API_URL}. Start it with: uvicorn backend.app.main:app --reload"

# ---- read-only catalog summary (the page still works if these calls fail) ----
genres, popular = [], []
if api_ok:
    try:
        genres = sorted(api_get("/catalog/genres"), key=lambda g: -g["count"])
    except Exception:
        genres = []
    try:
        popular = api_get("/popular", n=4)
    except Exception:
        popular = []

total_works = sum(g["count"] for g in genres)
meta = [f"{total_works:,} works", f"{len(genres)} genres"] if genres else None

main, side = st.columns([2.2, 1], gap="large")

with main:
    ui.hero(
        "Search, browse and explore the catalog of Alexandria",
        "Find a work even with a typo, follow who influenced whom, and watch what readers open.",
        "pages/1_Search.py",
        "Start searching",
        meta,
    )

    ui.section_title("Largest genres", "Share of the catalog")
    if genres:
        cols = st.columns(3)
        for col, g, tone in zip(cols, genres[:3], ("lav", "orange", "pink")):
            share = 100 * g["count"] / total_works if total_works else 0
            with col:
                ui.show(
                    ui.stat_card(
                        g["genre"].capitalize(),
                        f"{g['count']:,}",
                        hint=f"{share:.0f}% of the catalog",
                        tone=tone,
                        pct=share,
                    )
                )
    else:
        with ui.card():
            ui.empty_state("No catalog data yet", "Genre statistics appear here once the catalog API answers.")

    ui.section_title("Most read right now", "Redis sorted set")
    if popular:
        cols = st.columns(len(popular))
        for col, rank, row in zip(cols, range(1, 5), popular):
            with col:
                with ui.card():
                    ui.show(
                        ui.cover(row["title"], "", "wide")
                        + f'<div class="pk-card-meta"><b>#{rank}</b> · {ui.esc(row["views"])} views</div>'
                    )
    else:
        with ui.card():
            ui.empty_state(
                "No view yet",
                "Open a work in the Browse page, then come back here.",
            )

with side:
    ui.show(ui.status(api_ok, api_message))
    ui.section_title("Explore")
    for page, title, text in (
        ("pages/4_Graph.py", "Graph", "Who influenced whom: paths between authors and PageRank (Neo4j)."),
        ("pages/5_Events.py", "Events", "Reads per day and reading history (Cassandra)."),
        ("pages/6_Monitoring.py", "Monitoring", "API logs in Kibana and bot alerts (ELK)."),
    ):
        with ui.card():
            ui.show(f'<div class="pk-link-title">{ui.esc(title)}</div><div class="pk-link-text">{ui.esc(text)}</div>')
            ui.page_link(page, label=f"Open {title}", icon=":material/arrow_forward:")
