"""Day 4 check for member B. Start the API and `python scripts/zscore_alert.py`, run the bot,
then from the repo root:
    python scripts/check_day4_b.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from backend.app.config import settings  # noqa: E402

API = "http://localhost:8000"
KIBANA = "http://localhost:5601"
ROOT = Path(__file__).resolve().parents[1]
problems = []


def check(ok: bool, text: str):
    print(("[OK]   " if ok else "[FAIL] ") + text)
    if not ok:
        problems.append(text)


try:
    es = settings.es_logs_url
    r = httpx.get(f"{es}/_ilm/policy/pinakes-logs-7d", timeout=15)
    days = r.json().get("pinakes-logs-7d", {}).get("policy", {}).get("phases", {}).get("delete", {})
    check(
        r.status_code == 200 and days.get("min_age") == "7d",
        f"ILM policy: delete after {days.get('min_age')}",
    )
    t = httpx.get(f"{es}/_index_template/pinakes-logs", timeout=15).json()
    settings_ = t["index_templates"][0]["index_template"]["template"]["settings"]
    check("pinakes-logs-7d" in str(settings_), "index template uses the 7-day policy")
except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
    check(False, f"ILM / template not readable: {exc.__class__.__name__}")

try:
    r = httpx.get(f"{API}/monitoring/alerts", params={"limit": 5}, timeout=15)
    alerts = r.json() if r.status_code == 200 else []
    check(
        r.status_code == 200 and len(alerts) > 0,
        f"GET /monitoring/alerts -> {r.status_code}, {len(alerts)} alert(s)",
    )
    for a in alerts[:3]:
        ip, rate, z = a["client_ip"], a["requests_per_min"], a["z_score"]
        print(f"         {a['ts']}  {ip}  {rate} req/min  z={z}")
    check(all(a["z_score"] > 3 for a in alerts), "every alert has z > 3")
except (httpx.HTTPError, ValueError, KeyError) as exc:
    check(False, f"API not reachable ({exc.__class__.__name__}). uvicorn is not running?")

try:
    r = httpx.get(f"{KIBANA}/api/saved_objects/_find", params={"type": "dashboard"}, timeout=15)
    total = r.json().get("total", 0)
    check(total >= 1, f"Kibana: {total} dashboard(s)")
except (httpx.HTTPError, ValueError):
    check(False, "Kibana not reachable on port 5601")

export = ROOT / "elk" / "dashboard.ndjson"
check(
    export.exists() and export.stat().st_size > 0,
    "elk/dashboard.ndjson exists (python elk/dashboard_io.py export)",
)

sys.exit(1 if problems else 0)
