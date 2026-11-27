import os
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd
import streamlit as st

import ui

API_URL = os.getenv("API_URL", "http://localhost:8000")

ui.setup(
    "events",
    "Events",
    "Reading events stored in Cassandra: reads of a work per day, and a reading history.",
)


def api_get(path: str, **params):
    params = {k: v for k, v in params.items() if v not in (None, "")}
    r = httpx.get(f"{API_URL}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def api_post(path: str, body: dict):
    r = httpx.post(f"{API_URL}{path}", json=body, timeout=15)
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
    c_work, c_user, c_days = st.columns([1, 1, 1.4])
    work_id = c_work.text_input("Work id", value="w_0003").strip()
    user_id = c_user.text_input("User id", value="u_42").strip()
    days = c_days.slider("Days to show", 3, 30, 7)

    # ---- record one read (the same call the Browse and Popular pages make) ----
    if st.button("Record one read of this work by this user"):
        if not work_id or not user_id:
            st.warning("Fill in the work id and the user id.")
        else:
            try:
                api_post("/events/read", {"work_id": work_id, "user_id": user_id})
                st.success("Read recorded.")
            except Exception as exc:
                show_error(exc)

# ---- reads per day ----
ui.section_title("Reads per day", "UTC days")
if work_id:
    today = datetime.now(timezone.utc).date()  # the API counts days in UTC
    rows = []
    try:
        for back in range(days - 1, -1, -1):
            day = (today - timedelta(days=back)).isoformat()
            rows.append(
                {
                    "day": day,
                    "reads": api_get(f"/events/work/{work_id}", day=day)["count"],
                }
            )
    except Exception as exc:
        show_error(exc)
    else:
        left, right = st.columns([1, 2.2], gap="large")
        with left:
            ui.show(ui.stat_card(f"Reads of {work_id} today (UTC)", rows[-1]["reads"], tone="lav"))
            ui.show(
                '<div style="height:.8rem"></div>'
                + ui.stat_card(
                    f"Last {days} days",
                    sum(r["reads"] for r in rows),
                    hint=f"{sum(r['reads'] for r in rows)} reads in the last {days} days.",
                    tone="orange",
                )
            )
        with right, ui.card():
            st.bar_chart(pd.DataFrame(rows), x="day", y="reads", color="#8F84E8")
else:
    with ui.card():
        ui.empty_state("Enter a work id", "For example w_0003.")

# ---- history of one user ----
ui.section_title("Reading history of a user", "Latest 20 reads")
if user_id:
    try:
        history = api_get(f"/events/user/{user_id}", limit=20)
    except Exception as exc:
        show_error(exc)
    else:
        with ui.card():
            if history:
                ui.show(ui.table(["Work", "Read at (UTC)"], [[h["work_id"], h["ts"]] for h in history]))
            else:
                ui.empty_state(f"No read event for {user_id}", "Reads appear here once this user opens a work.")
else:
    with ui.card():
        ui.empty_state("Enter a user id", "For example u_42.")
