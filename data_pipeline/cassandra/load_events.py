"""Create the Cassandra tables and load fake reading events (task B5, owner: B).

Run from the repo root, with stack B started (Cassandra needs 1 to 2 minutes to start):
    python -m data_pipeline.cassandra.load_events --schema-only     # tables only
    python -m data_pipeline.cassandra.load_events                   # tables + 100,000 events
    python -m data_pipeline.cassandra.load_events --events 20000 --truncate
Works are taken from --works (their ids). Some works are read much more than others
(Zipf law), so 'most read' lists look realistic.
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args

from backend.app.config import settings

SCHEMA = Path(__file__).with_name("schema.cql")
CHUNK = 5000


def read_statements(path: Path = SCHEMA) -> list[str]:
    lines = [
        ln
        for ln in path.read_text(encoding="utf-8").splitlines()
        if not ln.strip().startswith("--")
    ]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def generate_events(work_ids, n_events, n_users=500, days=30, now=None, seed=42):
    """Yield (work_id, user_id, ts). Work popularity follows 1/rank, time is uniform."""
    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    weights = [1.0 / (rank + 1) for rank in range(len(work_ids))]
    works = rng.choices(work_ids, weights=weights, k=n_events)
    span = days * 24 * 3600
    for work_id in works:
        user = f"u_{rng.randint(1, n_users)}"
        ts = now - timedelta(seconds=rng.randint(0, span), milliseconds=rng.randint(0, 999))
        yield work_id, user, ts


def connect(retries=20, delay=5):
    hosts = [h.strip() for h in settings.cassandra_hosts.split(",") if h.strip()]
    for attempt in range(1, retries + 1):
        try:
            return Cluster(hosts, connect_timeout=10).connect()
        except Exception as exc:  # Cassandra still starting
            print(f"Cassandra not ready ({attempt}/{retries}): {exc.__class__.__name__}")
            time.sleep(delay)
    sys.exit("Cannot reach Cassandra. Check: docker compose -p pinakes-b -f docker/stack-b.yml ps")


def load_work_ids(path: str) -> list[str]:
    p = Path(path)
    if p.exists():
        return [w["_id"] for w in json.loads(p.read_text(encoding="utf-8"))]
    print(f"{path} not found: using w_0001 to w_0020")
    return [f"w_{i:04d}" for i in range(1, 21)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--works", default="data/sample/works_sample.json")
    ap.add_argument("--events", type=int, default=100_000)
    ap.add_argument("--users", type=int, default=500)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--schema-only", action="store_true")
    ap.add_argument("--truncate", action="store_true", help="empty both tables first")
    args = ap.parse_args()

    session = connect()
    for statement in read_statements():
        session.execute(statement)
    print("Keyspace and tables are ready.")
    if args.schema_only:
        return
    if args.truncate:
        session.execute("TRUNCATE pinakes.reads_by_work_day")
        session.execute("TRUNCATE pinakes.reads_by_user")
        print("Tables emptied.")

    by_work = session.prepare(
        "INSERT INTO pinakes.reads_by_work_day (work_id, day, ts, user_id) VALUES (?, ?, ?, ?)"
    )
    by_user = session.prepare(
        "INSERT INTO pinakes.reads_by_user (user_id, ts, work_id) VALUES (?, ?, ?)"
    )
    events = generate_events(load_work_ids(args.works), args.events, args.users, args.days)
    done = errors = 0
    start = time.time()
    while True:
        chunk = [e for _, e in zip(range(CHUNK), events)]
        if not chunk:
            break
        for stmt, rows in (
            (by_work, [(w, ts.date(), ts, u) for w, u, ts in chunk]),
            (by_user, [(u, ts, w) for w, u, ts in chunk]),
        ):
            results = execute_concurrent_with_args(
                session, stmt, rows, concurrency=64, raise_on_first_error=False
            )
            errors += sum(1 for ok, _ in results if not ok)
        done += len(chunk)
        print(f"  {done} events ({time.time() - start:.0f} s)")
    print(f"Done: {done} events written to 2 tables, {errors} failed writes.")
    sample = session.execute("SELECT user_id, ts, work_id FROM pinakes.reads_by_user LIMIT 3")
    for row in sample:
        print("  example:", row.user_id, row.ts, row.work_id)


if __name__ == "__main__":
    main()
