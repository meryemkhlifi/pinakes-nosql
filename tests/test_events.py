from datetime import date, datetime, timedelta, timezone

import pytest
from cassandra.cluster import NoHostAvailable
from fastapi.testclient import TestClient

from backend.app.db import cassandra as events_db
from backend.app.main import app
from data_pipeline.cassandra import load_events as le

client = TestClient(app)


@pytest.fixture
def fake_db(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        events_db, "record_read", lambda w, u: calls.setdefault("read", []).append((w, u))
    )
    monkeypatch.setattr(events_db, "reads_of_work", lambda w, d: calls.setdefault("day", d) and 14)
    monkeypatch.setattr(
        events_db,
        "reads_of_user",
        lambda u, n: [{"work_id": "w_0003", "ts": "2026-11-20T10:15:00Z"}][:n],
    )
    return calls


def test_post_read(fake_db):
    r = client.post("/events/read", json={"work_id": "w_0003", "user_id": "u_42"})
    assert r.status_code == 201 and r.json() == {"status": "recorded"}
    assert fake_db["read"] == [("w_0003", "u_42")]


def test_post_read_validates_body():
    assert client.post("/events/read", json={"work_id": "w_0003"}).status_code == 422
    assert client.post("/events/read", json={"work_id": "", "user_id": "u"}).status_code == 422


def test_get_work_with_and_without_day(fake_db):
    r = client.get("/events/work/w_0003", params={"day": "2026-11-20"})
    assert r.json() == {"work_id": "w_0003", "day": "2026-11-20", "count": 14}
    assert fake_db["day"] == date(2026, 11, 20)
    today = client.get("/events/work/w_0003").json()["day"]
    assert today == datetime.now(timezone.utc).date().isoformat()
    assert client.get("/events/work/w_0003", params={"day": "not-a-date"}).status_code == 422


def test_get_user_and_limit(fake_db):
    r = client.get("/events/user/u_42?limit=5")
    assert r.json() == [{"work_id": "w_0003", "ts": "2026-11-20T10:15:00Z"}]
    assert client.get("/events/user/u_42?limit=0").status_code == 422


def test_cassandra_down_is_503(monkeypatch):
    def boom(*args):
        raise NoHostAvailable("down", {})

    monkeypatch.setattr(events_db, "reads_of_user", boom)
    r = client.get("/events/user/u_1")
    assert r.status_code == 503 and "load_events" in r.json()["detail"]


def test_format_ts():
    assert events_db.format_ts(datetime(2026, 11, 20, 10, 15, 0, 999000)) == "2026-11-20T10:15:00Z"


class FakeFuture:
    def result(self):
        return None


class FakeSession:
    def __init__(self):
        self.writes = []

    def execute_async(self, statement, params):
        self.writes.append((statement, params))
        return FakeFuture()


def test_record_read_writes_both_tables(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(events_db, "get_db", lambda: (session, {"by_work": "W", "by_user": "U"}))
    ts = datetime(2026, 11, 20, 23, 59, 59, tzinfo=timezone.utc)
    events_db.record_read("w_1", "u_1", ts)
    assert session.writes == [
        ("W", ("w_1", date(2026, 11, 20), ts, "u_1")),
        ("U", ("u_1", ts, "w_1")),
    ]


# ---- loader ----


def test_schema_has_keyspace_and_two_tables():
    statements = le.read_statements()
    assert len(statements) == 3
    assert statements[0].startswith("CREATE KEYSPACE")
    assert "PRIMARY KEY ((work_id, day), ts, user_id)" in statements[1]
    assert "PRIMARY KEY (user_id, ts, work_id)" in statements[2]


def test_generate_events():
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    works = [f"w_{i:04d}" for i in range(1, 21)]
    events = list(le.generate_events(works, 5000, n_users=50, days=10, now=now, seed=1))
    assert len(events) == 5000
    assert all(now - timedelta(days=10, seconds=1) <= ts <= now for _, _, ts in events)
    assert {u for _, u, _ in events} <= {f"u_{i}" for i in range(1, 51)}
    counts = {}
    for w, _, _ in events:
        counts[w] = counts.get(w, 0) + 1
    assert counts["w_0001"] > 3 * counts["w_0020"]  # popular works are read more
    assert events == list(le.generate_events(works, 5000, n_users=50, days=10, now=now, seed=1))
