"""Streamlit pages, run with a fake API (no server needed)."""

from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
SEARCH_PAGE = str(ROOT / "frontend" / "pages" / "1_Search.py")
BROWSE_PAGE = str(ROOT / "frontend" / "pages" / "2_Browse.py")
POPULAR_PAGE = str(ROOT / "frontend" / "pages" / "3_Popular.py")

GENRES = [{"genre": "philosophy", "count": 3}, {"genre": "epic", "count": 4}]
AUTHORS = [
    {
        "author_id": "a_plato",
        "name": "Plato",
        "works": [{"id": "w_0003", "title": "The Republic"}],
    }
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
POPULAR = [
    {"id": "w_0003", "title": "The Republic", "views": 12},
    {"id": "w_0001", "title": "Iliad", "views": 5},
]
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
    def __init__(self, fail=None, fail_post=None, authors=None):
        self.calls = []
        self.posts = []
        self.fail = fail
        self.fail_post = fail_post
        self.authors = authors or AUTHORS

    def __call__(self, url, params=None, timeout=None):
        path = url.split("localhost:8000", 1)[1]
        self.calls.append((path, params or {}))
        request = httpx.Request("GET", url)
        if self.fail:
            return httpx.Response(self.fail, json={"detail": "boom"}, request=request)
        routes = {
            "/catalog/genres": GENRES,
            "/catalog/genres/philosophy/authors": self.authors,
            "/catalog/genres/epic/authors": self.authors,
            "/catalog/works/w_0003": WORK,
            "/catalog/works/w_0001": {**WORK, "_id": "w_0001", "title": "Iliad"},
            "/suggest": ["The Republic"],
            "/search": SEARCH,
            "/popular": POPULAR,
        }
        return httpx.Response(200, json=routes[path], request=request)

    def post(self, url, json=None, timeout=None):
        path = url.split("localhost:8000", 1)[1]
        self.posts.append((path, json))
        request = httpx.Request("POST", url)
        if self.fail_post:
            return httpx.Response(self.fail_post, json={"detail": "down"}, request=request)
        return httpx.Response(201, json={"status": "recorded"}, request=request)


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(httpx, "get", fake)
    monkeypatch.setattr(httpx, "post", fake.post)
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
    assert api.posts == []  # no read event yet
    at.button[0].click().run()
    assert not at.exception
    assert [c[0] for c in api.calls].count("/catalog/works/w_0003") == 1
    assert at.subheader[0].value == "The Republic"
    assert "Piraeus" in text_of(at)
    assert api.posts == [("/events/read", {"work_id": "w_0003", "user_id": "u_42"})]


def test_browse_page_uses_the_reader_id(api):
    at = AppTest.from_file(BROWSE_PAGE, default_timeout=15).run()
    at.text_input[0].set_value("u_7").run()
    at.button[0].click().run()
    assert api.posts == [("/events/read", {"work_id": "w_0003", "user_id": "u_7"})]


def test_browse_page_keeps_two_works_with_the_same_title(monkeypatch):
    twins = [
        {
            "author_id": "a_homer",
            "name": "Homer",
            "works": [
                {"id": "w_0001", "title": "Iliad"},
                {"id": "w_0099", "title": "Iliad"},
            ],
        }
    ]
    fake = FakeApi(authors=twins)
    monkeypatch.setattr(httpx, "get", fake)
    monkeypatch.setattr(httpx, "post", fake.post)
    at = AppTest.from_file(BROWSE_PAGE, default_timeout=15).run()
    assert not at.exception
    assert at.selectbox[2].options == ["Iliad [w_0001]", "Iliad [w_0099]"]


def test_browse_page_still_shows_the_work_when_the_event_fails(monkeypatch):
    fake = FakeApi(fail_post=503)
    monkeypatch.setattr(httpx, "get", fake)
    monkeypatch.setattr(httpx, "post", fake.post)
    at = AppTest.from_file(BROWSE_PAGE, default_timeout=15).run()
    at.button[0].click().run()
    assert not at.exception
    assert at.subheader[0].value == "The Republic"
    assert any("not recorded" in w.value for w in at.warning)


def test_browse_page_api_down(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeApi(fail=503))
    at = AppTest.from_file(BROWSE_PAGE, default_timeout=15).run()
    assert not at.exception and any("503" in e.value for e in at.error)


def test_popular_page_lists_works_and_records_a_read(api):
    at = AppTest.from_file(POPULAR_PAGE, default_timeout=15).run()
    assert not at.exception
    assert at.dataframe[0].value["Title"].tolist() == ["The Republic", "Iliad"]
    assert at.dataframe[0].value["Views"].tolist() == [12, 5]
    assert api.posts == []
    at.button[0].click().run()
    assert not at.exception
    assert [c[0] for c in api.calls].count("/catalog/works/w_0003") == 1
    assert api.posts == [("/events/read", {"work_id": "w_0003", "user_id": "u_42"})]
    assert at.subheader[0].value == "The Republic"


def test_popular_page_empty_list(monkeypatch):
    fake = FakeApi()
    original = fake.__call__

    def empty(url, params=None, timeout=None):
        if url.endswith("/popular"):
            return httpx.Response(200, json=[], request=httpx.Request("GET", url))
        return original(url, params, timeout)

    monkeypatch.setattr(httpx, "get", empty)
    at = AppTest.from_file(POPULAR_PAGE, default_timeout=15).run()
    assert not at.exception
    assert any("No view yet" in i.value for i in at.info)


def test_popular_page_redis_down(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeApi(fail=503))
    at = AppTest.from_file(POPULAR_PAGE, default_timeout=15).run()
    assert not at.exception and any("503" in e.value for e in at.error)
