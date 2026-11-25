"""The Day 5 integration script, run against a fake API that behaves like the real one."""

import importlib.util
import json
from pathlib import Path

import httpx

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_day5_demo.py"
spec = importlib.util.spec_from_file_location("check_day5_demo", SCRIPT)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

HITS = [
    {
        "id": "w_0003",
        "title": "The Republic",
        "genre": "philosophy",
        "authors": ["Plato"],
    }
]


class FakeServer:
    """Counts views and reads like Redis and Cassandra do."""

    def __init__(self, cache=True, count_views=True, alerts=None, broken=None):
        self.views, self.reads, self.users = {}, 0, []
        self.seen_search = set()
        self.cache, self.count_views = cache, count_views
        self.alerts = alerts or []
        self.broken = broken

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, dict(request.url.params)
        if self.broken and path.startswith(self.broken):
            return httpx.Response(503, json={"detail": "down"})
        if path == "/search":
            key = json.dumps(params, sort_keys=True)
            header = {"X-Cache": "HIT" if self.cache and key in self.seen_search else "MISS"}
            self.seen_search.add(key)
            body = {
                "total": 1,
                "hits": HITS,
                "facets": {"genre": [{"key": "philosophy", "count": 1}]},
            }
            return httpx.Response(200, json=body, headers=header)
        if path == "/suggest":
            return httpx.Response(200, json=["The Republic"])
        if path == "/graph/influence/top":
            return httpx.Response(
                200, json=[{"author_id": "a_plato", "name": "Plato", "score": 0.2}]
            )
        if path == "/graph/neighbors/a_plato":
            edge = {"source": "a_aristotle", "target": "a_plato", "type": "STUDENT_OF"}
            return httpx.Response(200, json={"nodes": [], "edges": [edge]})
        if path == "/graph/path":
            if params["to"] == "a_does_not_exist":
                return httpx.Response(404, json={"detail": "Author not found"})
            nodes = [
                {"id": "a_plato", "name": "Plato"},
                {"id": "a_aristotle", "name": "Aristotle"},
            ]
            return httpx.Response(
                200, json={"found": True, "length": 1, "nodes": nodes, "edges": [{}]}
            )
        if path == "/catalog/genres":
            return httpx.Response(200, json=[{"genre": g, "count": 3} for g in "abcde"])
        if path.endswith("/authors"):
            return httpx.Response(
                200,
                json=[
                    {
                        "author_id": "a_plato",
                        "works": [{"id": "w_0003", "title": "The Republic"}],
                    }
                ],
            )
        if path == "/catalog/works/w_0003":
            if self.count_views:
                self.views["w_0003"] = self.views.get("w_0003", 0) + 1
            return httpx.Response(200, json={"_id": "w_0003", "title": "The Republic"})
        if path == "/popular":
            return httpx.Response(
                200,
                json=[{"id": i, "title": i, "views": v} for i, v in self.views.items()],
            )
        if path == "/events/read":
            self.reads += 1
            self.users.append(json.loads(request.content)["user_id"])
            return httpx.Response(201, json={"status": "recorded"})
        if path == "/events/work/w_0003":
            return httpx.Response(200, json={"work_id": "w_0003", "count": self.reads})
        if path.startswith("/events/user/"):
            return httpx.Response(
                200,
                json=[{"work_id": "w_0003", "ts": "2026-11-25T10:00:00Z"}] * self.reads,
            )
        if path == "/monitoring/alerts":
            return httpx.Response(200, json=self.alerts)
        return httpx.Response(404, json={"detail": "unknown"})


def run(server, **kwargs):
    client = httpx.Client(base_url="http://api", transport=httpx.MockTransport(server))
    return demo.run(client, **kwargs)


def test_everything_ok():
    report = run(FakeServer())
    assert report.problems == []


def test_missing_redis_cache_is_reported():
    report = run(FakeServer(cache=False))
    assert any("served from Redis" in p for p in report.problems)


def test_views_that_do_not_move_are_reported():
    report = run(FakeServer(count_views=False))
    assert any("most read" in p for p in report.problems)


def test_a_dead_service_is_one_fail_not_a_crash():
    report = run(FakeServer(broken="/events"))
    assert any("/events" in p and "503" in p for p in report.problems)
    assert not any("Plato" in p for p in report.problems)  # the other scenarios still ran


def test_expect_alerts():
    assert any("alert with z" in p for p in run(FakeServer(), expect_alerts=True).problems)
    alert = {
        "ts": "t",
        "client_ip": "203.0.113.50",
        "requests_per_min": 300,
        "z_score": 4.2,
    }
    assert run(FakeServer(alerts=[alert]), expect_alerts=True).problems == []
