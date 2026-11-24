import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
PAGE_SIZE = 10
YEAR_MIN, YEAR_MAX = -800, 2000
LANGUAGES = ["(all)", "en", "fr", "la", "grc"]


def api_get(path: str, **params):
    params = {k: v for k, v in params.items() if v not in (None, "")}
    r = httpx.get(f"{API_URL}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def show_error(exc: Exception):
    if isinstance(exc, httpx.HTTPStatusError):
        st.error(f"API error {exc.response.status_code}: {exc.response.json().get('detail', '')}")
    else:
        st.error(f"API not reachable at {API_URL}. Start it with: uvicorn backend.app.main:app")


st.title("Search")

genres = ["(all)"]
try:
    genres += [g["genre"] for g in api_get("/catalog/genres")]
except Exception:
    pass  # the filter just stays empty; the search itself reports the problem

with st.sidebar:
    st.header("Filters")
    genre = st.selectbox("Genre", genres)
    language = st.selectbox("Language", LANGUAGES)
    years = st.slider("Year", YEAR_MIN, YEAR_MAX, (YEAR_MIN, YEAR_MAX))

q = st.text_input("Search the catalog", placeholder="try a typo: republc")

if len(q.strip()) >= 2:
    try:
        suggestions = api_get("/suggest", q=q.strip())
        if suggestions:
            st.caption("Suggestions: " + "  ·  ".join(suggestions))
    except Exception:
        pass

if q.strip():
    page = st.number_input("Page", min_value=1, value=1, step=1)
    try:
        result = api_get(
            "/search",
            q=q.strip(),
            genre=None if genre == "(all)" else genre,
            language=None if language == "(all)" else language,
            year_from=years[0] if years[0] != YEAR_MIN else None,
            year_to=years[1] if years[1] != YEAR_MAX else None,
            page=int(page),
            size=PAGE_SIZE,
        )
    except Exception as exc:
        show_error(exc)
    else:
        st.write(f"**{result['total']}** results")
        for hit in result["hits"]:
            authors = ", ".join(hit["authors"])
            year = hit.get("year")
            st.markdown(f"**{hit['title']}**  \n{authors} · {hit['genre']} · {year}")
            for fragments in hit.get("highlight", {}).values():
                for fragment in fragments:
                    # the API escapes the text: <em> is the only tag, so this is safe
                    st.markdown(f"> {fragment}", unsafe_allow_html=True)
        facets = result.get("facets", {})
        with st.sidebar:
            st.header("Facets")
            for name in ("genre", "language"):
                if facets.get(name):
                    st.caption(name.capitalize())
                    for f in facets[name]:
                        st.write(f"{f['key']}: {f['count']}")
