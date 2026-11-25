import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
REFRESH_SECONDS = 3


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
    """The 'most read' table. It can refresh itself (see the Live box)."""
    try:
        rows = api_get("/popular", n=n)
    except Exception as exc:
        show_error(exc)
        return
    if not rows:
        st.info("No view yet. Open a work in the Browse page, then come back here.")
        return
    st.dataframe(
        [
            {"Rank": i, "Title": r["title"], "Views": r["views"], "Id": r["id"]}
            for i, r in enumerate(rows, 1)
        ],
        hide_index=True,
    )


st.title("Most read")
st.caption("Works ranked by number of views (Redis sorted set).")

n = st.slider("Number of works", 5, 30, 10)
live = st.checkbox(f"Live (refresh every {REFRESH_SECONDS} s)")
if live:
    st.fragment(run_every=REFRESH_SECONDS)(ranking)(n)
else:
    ranking(n)

st.header("Open a work")
try:
    top = api_get("/popular", n=n)
except Exception:
    top = []  # the error is already shown by the table above
if top:
    options = {f"{r['title']} [{r['id']}]": r["id"] for r in top}
    work_id = options[st.selectbox("Work", list(options))]
    user_id = st.text_input("Reader id (stored with the read event)", value="u_42").strip()
    if st.button("Open this work"):
        try:
            st.session_state["popular_opened"] = api_get(f"/catalog/works/{work_id}")  # +1 view
        except Exception as exc:
            show_error(exc)
        else:
            try:  # the read event goes to Cassandra. If it fails, the work is still shown.
                api_post(
                    "/events/read",
                    {"work_id": work_id, "user_id": user_id or "anonymous"},
                )
            except Exception as exc:
                st.warning(f"The read event was not recorded ({exc.__class__.__name__}).")
    work = st.session_state.get("popular_opened")
    if work:
        st.subheader(work["title"])
        st.write(
            ", ".join(a["name"] for a in work["authors"])
            + f" · {work['genre']} · {work.get('year')} · {work.get('language')}"
        )
        if work.get("incipit"):
            st.markdown(f"> {work['incipit']}")
