import os

import httpx
import streamlit as st

import ui

API_URL = os.getenv("API_URL", "http://localhost:8000")
REFRESH_SECONDS = 3

ui.setup("popular", "Most read", "Works ranked by number of views (Redis sorted set).")


def api_get(path: str, **params):
    r = httpx.get(f"{API_URL}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def api_post(path: str, body: dict):
    r = httpx.post(f"{API_URL}{path}", json=body, timeout=10)
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


def ranking(n: int):
    """The 'most read' ranking. It can refresh itself (see the Live box)."""
    try:
        rows = api_get("/popular", n=n)
    except Exception as exc:
        show_error(exc)
        return
    if not rows:
        with ui.card():
            ui.empty_state("No view yet", "Open a work in the Browse page, then come back here.")
        return
    top = max(r["views"] for r in rows) or 1
    podium = st.columns(min(3, len(rows)))
    for col, i, r, tone in zip(podium, range(1, 4), rows, ("lav", "orange", "pink")):
        with col:
            ui.show(
                ui.stat_card(
                    f"#{i}",
                    title=r["title"],
                    hint=f"{r['views']} views · {r['id']}",
                    tone=tone,
                    pct=100 * r["views"] / top,
                )
            )
    rest = rows[3:]
    if rest:
        with ui.card():
            items = [
                {"label": r["title"], "sub": r["id"], "value": f"{r['views']} views", "ratio": r["views"] / top}
                for r in rest
            ]
            ui.show(ui.rank_rows(items, start=4))  # continues the podium numbering


with ui.card():
    c_n, c_live = st.columns([2, 1], vertical_alignment="center")
    n = c_n.slider("Number of works", 5, 30, 10)
    live = c_live.checkbox(f"Live (refresh every {REFRESH_SECONDS} s)")

main, side = st.columns([1.6, 1], gap="large")

with main:
    if live:
        st.fragment(run_every=REFRESH_SECONDS)(ranking)(n)
    else:
        ranking(n)

with side:
    ui.section_title("Open a work")
    try:
        top = api_get("/popular", n=n)
    except Exception:
        top = []  # the error is already shown by the ranking above
    if top:
        with ui.card():
            options = {f"{r['title']} [{r['id']}]": r["id"] for r in top}
            work_id = options[st.selectbox("Work", list(options))]
            user_id = st.text_input("Reader id (stored with the read event)", value="u_42").strip()
            if st.button("Open this work"):
                try:
                    st.session_state["popular_opened"] = api_get(f"/catalog/works/{work_id}")  # +1 view
                except Exception as exc:
                    show_error(exc)
                else:
                    st.session_state.pop("popular_notice", None)
                    try:  # the read event goes to Cassandra. If it fails, the work is still shown.
                        api_post(
                            "/events/read",
                            {"work_id": work_id, "user_id": user_id or "anonymous"},
                        )
                    except Exception as exc:
                        st.session_state["popular_notice"] = (
                            f"The read event was not recorded ({exc.__class__.__name__})."
                        )
        work = st.session_state.get("popular_opened")
        if work:
            ui.work_detail(work, st.session_state.get("popular_notice"))
    else:
        with ui.card():
            ui.empty_state("Nothing to open yet", "The list fills up as works are opened.")
