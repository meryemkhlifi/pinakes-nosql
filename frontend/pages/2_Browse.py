import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")


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


def unique_labels(works: list[dict]) -> dict[str, str]:
    """{label: work_id}. Two works can share a title: the id is added to tell them apart."""
    counts: dict[str, int] = {}
    for w in works:
        counts[w["title"]] = counts.get(w["title"], 0) + 1
    return {
        (f"{w['title']} [{w['id']}]" if counts[w["title"]] > 1 else w["title"]): w["id"]
        for w in works
    }


st.title("Browse")
st.caption("Genre, then author, then works (MongoDB).")

try:
    genres = api_get("/catalog/genres")
except Exception as exc:
    show_error(exc)
    st.stop()

labels = {f"{g['genre']} ({g['count']})": g["genre"] for g in genres}
genre = labels[st.selectbox("1. Genre", list(labels))]

try:
    authors = api_get(f"/catalog/genres/{genre}/authors")
except Exception as exc:
    show_error(exc)
    st.stop()

by_id = {a["author_id"]: a for a in authors}
author_labels = {}
for a in authors:
    same_name = sum(1 for b in authors if b["name"] == a["name"])
    base = f"{a['name']} ({len(a['works'])})"
    author_labels[base if same_name == 1 else f"{base} [{a['author_id']}]"] = a["author_id"]
author = by_id[author_labels[st.selectbox("2. Author", list(author_labels))]]

works = unique_labels(author["works"])
work_id = works[st.selectbox("3. Work", list(works))]

user_id = st.text_input("Reader id (stored with the read event)", value="u_42").strip()

# A view is counted only when the button is pressed, not on every page refresh.
if st.button("Open this work"):
    try:
        st.session_state["opened"] = api_get(f"/catalog/works/{work_id}")  # +1 view in Redis
    except Exception as exc:
        show_error(exc)
    else:
        try:  # the read event goes to Cassandra. If it fails, the work is still shown.
            api_post("/events/read", {"work_id": work_id, "user_id": user_id or "anonymous"})
        except Exception as exc:
            st.warning(f"The read event was not recorded ({exc.__class__.__name__}).")

work = st.session_state.get("opened")
if work:
    st.subheader(work["title"])
    st.write(
        ", ".join(a["name"] for a in work["authors"])
        + f" · {work['genre']} · {work.get('year')} · {work.get('language')}"
    )
    for a in work["authors"]:
        if a.get("bio"):
            st.caption(f"{a['name']}: {a['bio']}")
    if work.get("incipit"):
        st.markdown(f"> {work['incipit']}")
    if work.get("subjects"):
        st.write("Subjects: " + ", ".join(work["subjects"]))
