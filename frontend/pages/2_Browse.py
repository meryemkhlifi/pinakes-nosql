import os

import httpx
import streamlit as st

import ui

API_URL = os.getenv("API_URL", "http://localhost:8000")
WORKS_PER_PAGE = 9

ui.setup("browse", "Browse", "Genre, then author, then works (MongoDB).")


def api_get(path: str):
    r = httpx.get(f"{API_URL}{path}", timeout=10)
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


def open_work(work_id: str, user_id: str):
    """Same behaviour as the old 'Open this work' button: a view is counted only on click."""
    st.session_state.pop("opened_notice", None)
    try:
        st.session_state["opened"] = api_get(f"/catalog/works/{work_id}")  # +1 view in Redis
    except Exception as exc:
        show_error(exc)
        return
    try:  # the read event goes to Cassandra. If it fails, the work is still shown.
        api_post("/events/read", {"work_id": work_id, "user_id": user_id or "anonymous"})
    except Exception as exc:
        st.session_state["opened_notice"] = f"The read event was not recorded ({exc.__class__.__name__})."


# ---- 1. genre and 2. author ----
try:
    genres = api_get("/catalog/genres")
except Exception as exc:
    show_error(exc)
    st.stop()
if not genres:
    with ui.card():
        ui.empty_state("The catalog is empty", "Load works into MongoDB first, then come back.")
    st.stop()

labels = {f"{g['genre']} ({g['count']})": g["genre"] for g in genres}

with ui.card():
    c_genre, c_author, c_user = st.columns([1, 1, 0.8])
    genre = labels[c_genre.selectbox("1. Genre", list(labels))]

    try:
        authors = api_get(f"/catalog/genres/{genre}/authors")
    except Exception as exc:
        show_error(exc)
        st.stop()
    if not authors:
        c_author.selectbox("2. Author", [], placeholder="No author in this genre")
        author = None
    else:
        by_id = {a["author_id"]: a for a in authors}
        author_labels = {}
        for a in authors:
            same_name = sum(1 for b in authors if b["name"] == a["name"])
            base = f"{a['name']} ({len(a['works'])})"
            author_labels[base if same_name == 1 else f"{base} [{a['author_id']}]"] = a["author_id"]
        author = by_id[author_labels[c_author.selectbox("2. Author", list(author_labels))]]
    user_id = c_user.text_input("Reader id (stored with the read event)", value="u_42").strip()

if author is None:
    with ui.card():
        ui.empty_state("No author in this genre", "Pick another genre.")
    st.stop()

works_all = author["works"]
main, side = st.columns([1.7, 1], gap="large")

# ---- 3. works of the author (one card per work; 'Open' = the old button) ----
with main:
    ui.section_title(f"Works by {author['name']}", f"{len(works_all)} in {genre}")
    pages = max(1, -(-len(works_all) // WORKS_PER_PAGE))
    page = 1
    if pages > 1:
        page = st.number_input("Page", min_value=1, max_value=pages, value=1, step=1)
    start = (int(page) - 1) * WORKS_PER_PAGE
    shown = works_all[start : start + WORKS_PER_PAGE]
    if not shown:
        with ui.card():
            ui.empty_state("No work", "This author has no work in this genre.")
    for row_start in range(0, len(shown), 3):
        cols = st.columns(3)
        for col, w in zip(cols, shown[row_start : row_start + 3]):
            with col, ui.card():
                ui.show(
                    ui.cover(w["title"], genre)
                    + f'<div class="pk-card-meta">{ui.esc(author["name"])} · {ui.esc(w["id"])}</div>'
                )
                if st.button("Open", key=f"open_{w['id']}"):
                    open_work(w["id"], user_id)

# ---- opened work ----
with side:
    ui.section_title("Reading")
    work = st.session_state.get("opened")
    if work:
        ui.work_detail(work, st.session_state.get("opened_notice"))
    else:
        with ui.card():
            ui.empty_state("Nothing open yet", "Press Open on a work to read its first line and author bio.")
