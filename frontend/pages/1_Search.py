import os

import httpx
import streamlit as st

import ui

API_URL = os.getenv("API_URL", "http://localhost:8000")
PAGE_SIZE = 10
YEAR_MIN, YEAR_MAX = -800, 2000
LANGUAGES = ["(all)", "en", "fr", "la", "grc"]

ui.setup(
    "search",
    "Search",
    "Typo-tolerant full-text search with filters and highlights (Elasticsearch).",
)


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


genres = ["(all)"]
try:
    genres += [g["genre"] for g in api_get("/catalog/genres")]
except Exception:
    pass  # the filter just stays empty; the search itself reports the problem

# ---- search bar + filters ----
with ui.card():
    q = st.text_input(
        "Search the catalog",
        placeholder="try a typo: republc",
        label_visibility="collapsed",
    )
    c_genre, c_lang, c_year, c_page = st.columns([1, 1, 1.5, 0.7])
    genre = c_genre.selectbox("Genre", genres)
    language = c_lang.selectbox("Language", LANGUAGES)
    years = c_year.slider("Year", YEAR_MIN, YEAR_MAX, (YEAR_MIN, YEAR_MAX))
    page = c_page.number_input("Page", min_value=1, value=1, step=1) if q.strip() else 1

if len(q.strip()) >= 2:
    try:
        suggestions = api_get("/suggest", q=q.strip())
        if suggestions:
            ui.show(
                '<div class="pk-section-hint" style="margin-top:.8rem">Suggestions</div>'
                + ui.chips(suggestions, tone="lav")
            )
    except Exception:
        pass

if not q.strip():
    with ui.card():
        ui.empty_state(
            "Start typing to search",
            "Titles, first lines, authors and genres are searched. Typos are fine.",
        )
else:
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
        main, side = st.columns([2.4, 1], gap="large")
        with main:
            ui.show(f'<div class="pk-count"><b>{ui.esc(result["total"])}</b> results</div>')
            if not result["hits"]:
                with ui.card():
                    ui.empty_state("No result", "Try other words, or relax the genre, language and year filters.")
            for hit in result["hits"]:
                authors = ", ".join(hit["authors"])
                meta = " · ".join(p for p in (authors, ui.fmt_year(hit.get("year"))) if p)
                quotes = "".join(
                    f'<div class="pk-quote">{ui.safe_highlight(fragment)}</div>'
                    # the API escapes the text: <em> is the only tag it keeps
                    for fragments in hit.get("highlight", {}).values()
                    for fragment in fragments
                )
                ui.show(
                    '<div class="pk-result">'
                    + ui.cover(hit["title"], hit.get("genre", ""), "book")
                    + '<div class="pk-result-body">'
                    + f'<div class="pk-result-title">{ui.esc(hit["title"])}</div>'
                    + f'<div class="pk-result-meta">{ui.esc(meta)}</div>'
                    + ui.chips([hit.get("genre")], tone=ui.tone_for(hit.get("genre") or hit["title"]))
                    + quotes
                    + "</div></div>"
                )
        with side:
            facets = result.get("facets", {})
            if any(facets.get(name) for name in ("genre", "language")):
                with ui.card():
                    for name in ("genre", "language"):
                        rows = facets.get(name)
                        if rows:
                            top = max(f["count"] for f in rows) or 1
                            ui.show(
                                f'<div class="pk-detail-label" style="margin-top:.4rem">{ui.esc(name)}</div>'
                                + ui.rank_rows(
                                    [{"label": f["key"], "value": f["count"], "ratio": f["count"] / top} for f in rows],
                                    numbered=False,
                                )
                            )
