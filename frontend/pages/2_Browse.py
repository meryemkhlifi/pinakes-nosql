import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")


def api_get(path: str):
    r = httpx.get(f"{API_URL}{path}", timeout=10)
    r.raise_for_status()
    return r.json()


def show_error(exc: Exception):
    if isinstance(exc, httpx.HTTPStatusError):
        st.error(f"API error {exc.response.status_code}: {exc.response.json().get('detail', '')}")
    else:
        st.error(f"API not reachable at {API_URL}. Start it with: uvicorn backend.app.main:app")


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

by_name = {f"{a['name']} ({len(a['works'])})": a for a in authors}
author = by_name[st.selectbox("2. Author", list(by_name))]

works = {w["title"]: w["id"] for w in author["works"]}
title = st.selectbox("3. Work", list(works))

# A view is counted only when the button is pressed, not on every page refresh.
if st.button("Open this work"):
    try:
        st.session_state["opened"] = api_get(f"/catalog/works/{works[title]}")
    except Exception as exc:
        show_error(exc)

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
