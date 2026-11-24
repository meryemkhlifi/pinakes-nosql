"""Cassandra access for the reading events (owner: B). Used by routers/events.py.

Every event is written to two tables (one per question, see data_pipeline/cassandra/schema.cql).
"""

from datetime import date, datetime, timezone
from functools import lru_cache

from cassandra import ConsistencyLevel
from cassandra.cluster import Cluster

from backend.app.config import settings

INSERT_BY_WORK = (
    "INSERT INTO pinakes.reads_by_work_day (work_id, day, ts, user_id) VALUES (?, ?, ?, ?)"
)
INSERT_BY_USER = "INSERT INTO pinakes.reads_by_user (user_id, ts, work_id) VALUES (?, ?, ?)"
COUNT_BY_WORK = "SELECT COUNT(*) FROM pinakes.reads_by_work_day WHERE work_id = ? AND day = ?"
SELECT_BY_USER = "SELECT work_id, ts FROM pinakes.reads_by_user WHERE user_id = ? LIMIT ?"


@lru_cache(maxsize=1)
def get_db():
    """(session, prepared statements). A failed connection is not cached, so it is retried."""
    hosts = [h.strip() for h in settings.cassandra_hosts.split(",") if h.strip()]
    session = Cluster(hosts, connect_timeout=5).connect()
    prepared = {
        "by_work": session.prepare(INSERT_BY_WORK),
        "by_user": session.prepare(INSERT_BY_USER),
        "count": session.prepare(COUNT_BY_WORK),
        "history": session.prepare(SELECT_BY_USER),
    }
    for statement in prepared.values():
        statement.consistency_level = ConsistencyLevel.ONE
    return session, prepared


def format_ts(ts: datetime) -> str:
    """Cassandra gives a naive UTC datetime: 2026-11-20T10:15:00Z."""
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def record_read(work_id: str, user_id: str, ts: datetime | None = None) -> None:
    ts = ts or datetime.now(timezone.utc)
    session, st = get_db()
    futures = [
        session.execute_async(
            st["by_work"], (work_id, ts.astimezone(timezone.utc).date(), ts, user_id)
        ),
        session.execute_async(st["by_user"], (user_id, ts, work_id)),
    ]
    for f in futures:
        f.result()  # raises if a write failed


def reads_of_work(work_id: str, day: date) -> int:
    session, st = get_db()
    return session.execute(st["count"], (work_id, day)).one()[0]


def reads_of_user(user_id: str, limit: int = 20) -> list[dict]:
    session, st = get_db()
    rows = session.execute(st["history"], (user_id, limit))
    return [{"work_id": r.work_id, "ts": format_ts(r.ts)} for r in rows]
