import os
from datetime import datetime, timezone

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
KIBANA_URL = os.getenv("KIBANA_URL", "http://localhost:5601")
Z_THRESHOLD = 3.0


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


st.title("Monitoring")
st.caption("API logs in Kibana, and the bot alerts (z-score on requests per IP per minute).")

st.link_button("Open the Kibana dashboard", f"{KIBANA_URL}/app/dashboards")
st.caption(f"Kibana: {KIBANA_URL}  ·  Dashboard: Pinakes - API monitoring")

st.header("Latest alerts")
limit = st.slider("Number of alerts", 5, 100, 20)
st.button("Refresh")  # any click reruns the page, which reloads the alerts

try:
    alerts = api_get("/monitoring/alerts", limit=limit)
except Exception as exc:
    show_error(exc)
else:
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    if not alerts:
        st.info(
            "No alert yet. Run: python scripts/zscore_alert.py (one terminal) and "
            "python scripts/bot_simulator.py (another)."
        )
    else:
        worst = max(alerts, key=lambda a: a["z_score"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Alerts shown", len(alerts))
        c2.metric("Highest z-score", worst["z_score"])
        c3.metric("Top IP", worst["client_ip"])
        st.dataframe(
            [
                {
                    "Minute (UTC)": a["ts"],
                    "Client IP": a["client_ip"],
                    "Requests/min": a["requests_per_min"],
                    "z-score": a["z_score"],
                }
                for a in alerts
            ],
            hide_index=True,
        )
    st.caption(f"Loaded at {now} UTC. An alert means z = (x - mean) / std is above {Z_THRESHOLD}.")
