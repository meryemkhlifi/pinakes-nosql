"""Streamlit pages Graph, Events and Monitoring, run with a fake API (no server needed)."""

import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PAGE = str(ROOT / "frontend" / "pages" / "4_Graph.py")
EVENTS_PAGE = str(ROOT / "frontend" / "pages" / "5_Events.py")
MONITORING_PAGE = str(ROOT / "frontend" / "pages" / "6_Monitoring.py")

GENRES = [{"genre": "philosophy", "count": 3}]
AUTHORS = [
    {"author_id": "a_plato", "name": "Plato", "works": []},
    {"author_id": "a_aristotle", "name": "Aristotle", "works": []},
    {"author_id": "a_zeno", "name": "Zeno", "works": []},
]
PATH = {
    "found": True,
    "length": 1,
    "nodes": [
        {"id": "a_aristotle", "name": "Aristotle"},
        {"id": "a_plato", "name": "Plato"},
    ],
    "edges": [{"source": "a_aristotle", "target": "a_plato", "type": "STUDENT_OF"}],
}
NO_PATH = {"found": False, "length": None, "nodes": [], "edges": []}
TOP = [
    {"author_id": "a_plato", "name": "Plato", "score": 0.12},
    {"author_id": "a_homer", "name": "Homer", "score": 0.1},
]
NEIGHBORS = {
    "nodes": [
        {"id": "a_aristotle", "name": "Aristotle"},
        {"id": "a_plato", "name": "Plato"},
    ],
    "edges": [{"source": "a_aristotle", "target": "a_plato", "type": "STUDENT_OF"}],
}
ALERTS = [
    {
        "ts": "2026-11-25T10:15:00Z",
        "client_ip": "203.0.113.50",
        "requests_per_min": 300,
        "z_score": 4.2,
    },
    {
        "ts": "2026-11-25T10:14:00Z",
        "client_ip": "203.0.113.50",
        "requests_per_min": 120,
        "z_score": 3.1,
    },
]
HISTORY = [{"work_id": "w_0003", "ts": "2026-11-25T10:15:00Z"}]


class FakeApi:
    def __init__(self, fail=None, path=PATH, genres=GENRES, alerts=ALERTS, history=HISTORY):
        self.calls = []
        self.posts = []
        self.fail = fail
        self.path = path
        self.genres = genres
        self.alerts = alerts
        self.history = history

    def __call__(self, url, params=None, timeout=None):
        path = url.split("localhost:8000", 1)[1]
        self.calls.append((path, params or {}))
        request = httpx.Request("GET", url)
        if self.fail:
            return httpx.Response(self.fail, json={"detail": "boom"}, request=request)
        if path.startswith("/events/work/"):
            return httpx.Response(
                200,
                json={"work_id": "w_0003", "day": params["day"], "count": 7},
                request=request,
            )
        if path.startswith("/graph/neighbors/"):
            return httpx.Response(200, json=NEIGHBORS, request=request)
        if path.startswith("/catalog/genres/") and path.endswith("/authors"):
            return httpx.Response(200, json=AUTHORS, request=request)
        routes = {
            "/catalog/genres": self.genres,
            "/graph/path": self.path,
            "/graph/influence/top": TOP,
            "/events/user/u_42": self.history,
            "/monitoring/alerts": self.alerts,
        }
        return httpx.Response(200, json=routes[path], request=request)

    def post(self, url, json=None, timeout=None):
        path = url.split("localhost:8000", 1)[1]
        self.posts.append((path, json))
        return httpx.Response(201, json={"status": "recorded"}, request=httpx.Request("POST", url))


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(httpx, "get", fake)
    monkeypatch.setattr(httpx, "post", fake.post)
    return fake


def text_of(at):
    return " ".join(m.value for m in at.markdown) + " " + " ".join(c.value for c in at.caption)


# ---- Graph ----


def test_graph_page_path_and_pagerank(api):
    at = AppTest.from_file(GRAPH_PAGE, default_timeout=15).run()
    assert not at.exception
    assert at.selectbox[0].options == [
        "Aristotle",
        "Plato",
        "Zeno",
    ]  # sorted, from the catalog
    ranked = re.findall(r'pk-rank-label">([^<]+)<', text_of(at))
    assert ranked == ["Plato", "Homer"]  # PageRank ranking
    assert not [c for c in api.calls if c[0] == "/graph/path"]  # nothing before the click
    at.selectbox[0].select("Aristotle")
    at.selectbox[1].select("Plato")
    at.button[0].click().run()
    assert not at.exception
    call = [c for c in api.calls if c[0] == "/graph/path"][-1][1]
    assert call == {"from": "a_aristotle", "to": "a_plato"}
    assert any("1 link" in s.value for s in at.success)
    assert "<b>Aristotle</b><span>→</span><b>Plato</b><em>STUDENT_OF</em>" in text_of(at)


def test_graph_page_no_path(monkeypatch):
    fake = FakeApi(path=NO_PATH)
    monkeypatch.setattr(httpx, "get", fake)
    at = AppTest.from_file(GRAPH_PAGE, default_timeout=15).run()
    at.button[0].click().run()
    assert not at.exception
    assert any("No path" in w.value for w in at.warning)


def test_graph_page_neighbors(api):
    at = AppTest.from_file(GRAPH_PAGE, default_timeout=15).run()
    at.button[1].click().run()
    assert not at.exception
    call = [c for c in api.calls if c[0].startswith("/graph/neighbors/")][-1]
    assert call[0] == "/graph/neighbors/a_aristotle" and call[1] == {"depth": 1}
    assert "2 authors, 1 links" in text_of(at)


def test_graph_page_falls_back_to_pagerank_authors_without_catalog(monkeypatch):
    fake = FakeApi()
    original = fake.__call__

    def no_catalog(url, params=None, timeout=None):
        if "/catalog/" in url:
            return httpx.Response(503, json={"detail": "mongo"}, request=httpx.Request("GET", url))
        return original(url, params, timeout)

    monkeypatch.setattr(httpx, "get", no_catalog)
    at = AppTest.from_file(GRAPH_PAGE, default_timeout=15).run()
    assert not at.exception
    assert at.selectbox[0].options == ["Homer", "Plato"]


def test_graph_page_api_down(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeApi(fail=503))
    at = AppTest.from_file(GRAPH_PAGE, default_timeout=15).run()
    assert not at.exception and any("503" in e.value for e in at.error)


# ---- Events ----


def test_events_page_chart_history_and_record(api):
    at = AppTest.from_file(EVENTS_PAGE, default_timeout=15).run()
    assert not at.exception
    days = [c[1]["day"] for c in api.calls if c[0] == "/events/work/w_0003"]
    assert len(days) == 7 and days[-1] == datetime.now(timezone.utc).date().isoformat()
    body = text_of(at)
    assert 'pk-stat-value">7<' in body  # reads today
    assert 'pk-stat-value">49<' in body  # 7 reads x 7 days
    assert "<td>w_0003</td>" in body  # reading history table
    assert api.posts == []
    at.button[0].click().run()
    assert not at.exception
    assert api.posts == [("/events/read", {"work_id": "w_0003", "user_id": "u_42"})]
    assert any("recorded" in s.value for s in at.success)


def test_events_page_user_without_history(monkeypatch):
    fake = FakeApi(history=[])
    monkeypatch.setattr(httpx, "get", fake)
    at = AppTest.from_file(EVENTS_PAGE, default_timeout=15).run()
    assert not at.exception
    assert "No read event" in text_of(at)


def test_events_page_cassandra_down(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeApi(fail=503))
    at = AppTest.from_file(EVENTS_PAGE, default_timeout=15).run()
    assert not at.exception and any("503" in e.value for e in at.error)


# ---- Monitoring ----


def test_monitoring_page_shows_alerts_and_kibana_link(api):
    at = AppTest.from_file(MONITORING_PAGE, default_timeout=15).run()
    assert not at.exception
    body = text_of(at)
    assert body.count("<td>203.0.113.50</td>") == 2  # one row per alert
    assert 'pk-stat-label">Highest z-score</div><div class="pk-stat-value">4.2<' in body
    assert 'pk-stat-label">Top IP</div><div class="pk-stat-value">203.0.113.50<' in body
    assert [c for c in api.calls if c[0] == "/monitoring/alerts"][-1][1] == {"limit": 20}


def test_monitoring_page_without_alert(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeApi(alerts=[]))
    at = AppTest.from_file(MONITORING_PAGE, default_timeout=15).run()
    assert not at.exception
    assert "No alert yet" in text_of(at)


def test_monitoring_page_elasticsearch_down(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeApi(fail=503))
    at = AppTest.from_file(MONITORING_PAGE, default_timeout=15).run()
    assert not at.exception and any("503" in e.value for e in at.error)
