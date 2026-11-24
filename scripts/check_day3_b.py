"""Day 3 check for member B. Start the API first, then from the repo root:
    python scripts/check_day3_b.py
It checks Cassandra through the API, then Elasticsearch (logs) and the Kibana data view.
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from backend.app.config import settings  # noqa: E402

API = "http://localhost:8000"
KIBANA = "http://localhost:5601"
problems = []


def check(ok: bool, text: str):
    print(("[OK]   " if ok else "[FAIL] ") + text)
    if not ok:
        problems.append(text)


user = f"u_check_{uuid.uuid4().hex[:6]}"
try:
    r = httpx.post(f"{API}/events/read", json={"work_id": "w_0003", "user_id": user}, timeout=15)
    check(r.status_code == 201, f"POST /events/read -> {r.status_code} {r.text[:80]}")
    r = httpx.get(f"{API}/events/work/w_0003", timeout=15)
    check(
        r.status_code == 200 and r.json().get("count", 0) >= 1, f"GET /events/work -> {r.text[:90]}"
    )
    r = httpx.get(f"{API}/events/user/{user}", timeout=15)
    ok = r.status_code == 200 and [e["work_id"] for e in r.json()] == ["w_0003"]
    check(ok, f"GET /events/user/{user} -> {r.text[:90]}")
except httpx.HTTPError as exc:
    check(False, f"API not reachable ({exc.__class__.__name__}). uvicorn is not running?")

try:
    es = settings.es_logs_url
    total = httpx.get(f"{es}/pinakes-logs-*/_count", timeout=15).json().get("count", 0)
    check(total > 0, f"Elasticsearch (logs): {total} request documents")
    recent = httpx.post(
        f"{es}/pinakes-logs-*/_search",
        json={
            "size": 1,
            "sort": [{"@timestamp": "desc"}],
            "query": {"range": {"@timestamp": {"gte": "now-10m"}}},
        },
        timeout=15,
    ).json()["hits"]["hits"]
    check(bool(recent), "a log line from the last 10 minutes is indexed")
    if recent:
        doc = recent[0]["_source"]
        wanted = {"client_ip", "method", "path", "status", "latency_ms"}
        check(wanted <= set(doc), f"fields present: {sorted(wanted & set(doc))}")
except (httpx.HTTPError, KeyError, ValueError) as exc:
    check(False, f"Elasticsearch (logs) not usable: {exc.__class__.__name__}")

try:
    r = httpx.get(f"{KIBANA}/api/data_views/data_view/pinakes-logs", timeout=15)
    check(r.status_code == 200, f"Kibana data view 'pinakes-logs-*' -> {r.status_code}")
except httpx.HTTPError:
    check(False, "Kibana not reachable on port 5601")

sys.exit(1 if problems else 0)
