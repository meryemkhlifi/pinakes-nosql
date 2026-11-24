"""Streamlit pages, run with a fake API (no server needed)."""

from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
SEARCH_PAGE = str(ROOT / "frontend" / "pages" / "1_Search.py")
BROWSE_PAGE = str(ROOT / "frontend" / "pages" / "2_Browse.py")

GENRES = [{"genre": "philosophy", "count": 3}, {"genre": "epic", "count": 4}]
AUTHORS = [
    {"author_id": "a_plato", "name": "Plato", "works": [{"id": "w_0003", "title": "The Republic"}]}
]
WORK = {
    "_id": "w_0003",
    "title": "The Republic",
    "genre": "philosophy",
    "year": -375,
    "language": "en",
    "incipit": "I went down yesterday to the Piraeus",
    "subjects": ["Justice"],
    "authors": [{"id": "a_plato", "name": "Plato", "bio": "Athenian philosopher"}],
}
SEARCH = {
    "total": 1,
    "page": 1,
    "size": 10,
    "hits": [
        {
            "id": "w_0003",
            "title": "The Republic",
            "genre": "philosophy",
            "authors": ["Plato"],
            "year": -375,
            "score": 7.3,
            "highlight": {"incipit": ["I went down yesterday to the <em>Piraeus</em>"]},
        }
    ],
    "facets": {
        "genre": [{"key": "philosophy", "count": 1}],
        "language": [{"key": "en", "count": 1}],
    },
}


class FakeApi:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def __call__(self, url, params=None, timeout=None):
        path = url.split("localhost:8000", 1)[1]
        self.calls.append((path, params or {}))
        request = httpx.Request("GET", url)
        if self.fail:
            return httpx.Response(self.fail, json={"detail": "boom"}, request=request)
        routes = {
            "/catalog/genres": GENRES,
            "/catalog/genres/philosophy/authors": AUTHORS,
            "/catalog/genres/epic/authors": AUTHORS,
            "/catalog/works/w_0003": WORK,
            "/suggest": ["The Republic"],
            "/search": SEARCH,
        }
        return httpx.Response(200, json=routes[path], request=request)


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(httpx, "get", fake)
    return fake


def text_of(at):
    return " ".join(m.value for m in at.markdown) + " " + " ".join(c.value for c in at.caption)


def test_search_page_shows_results_highlight_and_facets(api):
    at = AppTest.from_file(SEARCH_PAGE, default_timeout=15).run()
    assert not at.exception
    at.text_input[0].set_value("republc").run()
    assert not at.exception
    body = text_of(at)
    assert "The Republic" in body and "<em>Piraeus</em>" in body and "Suggestions" in body
    search_call = [c for c in api.calls if c[0] == "/search"][-1][1]
    assert search_call["q"] == "republc" and "genre" not in search_call


def test_search_page_applies_the_genre_filter(api):
    at = AppTest.from_file(SEARCH_PAGE, default_timeout=15).run()
    at.text_input[0].set_value("republic").run()
    at.sidebar.selectbox[0].select("philosophy").run()
    assert [c for c in api.calls if c[0] == "/search"][-1][1]["genre"] == "philosophy"


def test_search_page_shows_api_errors(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeApi(fail=503))
    at = AppTest.from_file(SEARCH_PAGE, default_timeout=15).run()
    at.text_input[0].set_value("republic").run()
    assert not at.exception
    assert any("503" in e.value for e in at.error)


def test_browse_page_genre_author_work(api):
    at = AppTest.from_file(BROWSE_PAGE, default_timeout=15).run()
    assert not at.exception
    assert at.selectbox[0].options == ["philosophy (3)", "epic (4)"]
    assert at.selectbox[1].options == ["Plato (1)"]
    assert at.selectbox[2].options == ["The Republic"]
    assert not any(c[0].startswith("/catalog/works/") for c in api.calls)  # no view yet
    at.button[0].click().run()
    assert not at.exception
    assert [c[0] for c in api.calls].count("/catalog/works/w_0003") == 1
    assert at.subheader[0].value == "The Republic"
    assert "Piraeus" in text_of(at)


def test_browse_page_api_down(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeApi(fail=503))
    at = AppTest.from_file(BROWSE_PAGE, default_timeout=15).run()
    assert not at.exception and any("503" in e.value for e in at.error)
