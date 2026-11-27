import os
from datetime import datetime, timezone

import httpx
import streamlit as st

import ui

API_URL = os.getenv("API_URL", "http://localhost:8000")
KIBANA_URL = os.getenv("KIBANA_URL", "http://localhost:5601")
Z_THRESHOLD = 3.0

ui.setup(
    "monitoring",
    "Monitoring",
    "API logs in Kibana, and the bot alerts (z-score on requests per IP per minute).",
)


def api_get(path: str, **params):
    params = {k: v for k, v in params.items() if v not in (None, "")}
    r = httpx.get(f"{API_URL}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def show_error(exc: Exception):
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail", "")
        except ValueError:
            detail = exc.response.text[:200]
        st.error(f"API error {exc.response.status_code}: {detail}")
    else:
        st.error(f"API not reachable at {API_URL}. Start it with: uvicorn backend.app.main:app")


with ui.card():
    c_link, c_info = st.columns([1, 2], vertical_alignment="center")
    c_link.link_button("Open the Kibana dashboard", f"{KIBANA_URL}/app/dashboards")
    c_info.caption(f"Kibana: {KIBANA_URL}  ·  Dashboard: Pinakes - API monitoring")

ui.section_title("Latest alerts", f"Alert when z > {Z_THRESHOLD:g}")
with ui.card():
    c_limit, c_refresh = st.columns([3, 1], vertical_alignment="bottom")
    limit = c_limit.slider("Number of alerts", 5, 100, 20)
    c_refresh.button("Refresh")  # any click reruns the page, which reloads the alerts

try:
    alerts = api_get("/monitoring/alerts", limit=limit)
except Exception as exc:
    show_error(exc)
else:
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    if not alerts:
        with ui.card():
            ui.empty_state(
                "No alert yet",
                "Run: python scripts/zscore_alert.py (one terminal) and "
                "python scripts/bot_simulator.py (another).",
            )
    else:
        worst = max(alerts, key=lambda a: a["z_score"])
        c1, c2, c3 = st.columns(3)
        c1.markdown(ui.stat_card("Alerts shown", len(alerts), tone="lav"), unsafe_allow_html=True)
        c2.markdown(ui.stat_card("Highest z-score", worst["z_score"], tone="pink"), unsafe_allow_html=True)
        c3.markdown(ui.stat_card("Top IP", worst["client_ip"], tone="orange"), unsafe_allow_html=True)
        with ui.card():
            ui.show(
                ui.table(
                    ["Minute (UTC)", "Client IP", "Requests/min", "z-score"],
                    [
                        [
                            a["ts"],
                            a["client_ip"],
                            a["requests_per_min"],
                            ui.Raw(ui.chip(a["z_score"], "pink")),
                        ]
                        for a in alerts
                    ],
                )
            )
    st.caption(f"Loaded at {now} UTC. An alert means z = (x - mean) / std is above {Z_THRESHOLD}.")
