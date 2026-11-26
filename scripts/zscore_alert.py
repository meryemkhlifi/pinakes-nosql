"""Detect bots with a z-score and write alerts to Elasticsearch (task B7, owner: B).

For every (IP, minute) pair of the last --window minutes we count the requests x.
    z = (x - mean) / std        mean and std are computed over all the (IP, minute) counts
An alert is raised when z > 3 (and x is at least --min-requests, and the minute is recent).
Alerts go to the index `pinakes-alerts`; the API shows them in GET /monitoring/alerts.

    python scripts/zscore_alert.py              # check every 20 seconds, Ctrl+C to stop
    python scripts/zscore_alert.py --once       # one check, then stop
"""

import argparse
import os
import statistics
import time
from datetime import datetime, timedelta, timezone

import httpx

ALERT_INDEX = "pinakes-alerts"
ALERT_MAPPING = {
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "minute": {"type": "date"},
            "client_ip": {"type": "ip", "ignore_malformed": True},
            "requests_per_min": {"type": "integer"},
            "z_score": {"type": "float"},
            "mean": {"type": "float"},
            "std": {"type": "float"},
        }
    }
}


def fetch_counts(client: httpx.Client, es: str, window_minutes: int) -> list[tuple]:
    """[(minute start, client_ip, number of requests)] over the last window."""
    body = {
        "size": 0,
        "query": {"range": {"@timestamp": {"gte": f"now-{window_minutes}m"}}},
        "aggs": {
            "per_minute": {
                "date_histogram": {
                    "field": "@timestamp",
                    "fixed_interval": "1m",
                    "min_doc_count": 1,
                },
                "aggs": {"ips": {"terms": {"field": "client_ip", "size": 1000}}},
            }
        },
    }
    r = client.post(f"{es}/pinakes-logs-*/_search", json=body)
    r.raise_for_status()
    rows = []
    for minute in r.json()["aggregations"]["per_minute"]["buckets"]:
        start = datetime.fromtimestamp(minute["key"] / 1000, tz=timezone.utc)
        for ip in minute["ips"]["buckets"]:
            rows.append((start, ip["key"], ip["doc_count"]))
    return rows


def find_alerts(
    counts: list[tuple],
    threshold: float = 3.0,
    min_requests: int = 20,
    min_samples: int = 10,
    recent_minutes: int = 3,
    now: datetime | None = None,
) -> list[dict]:
    """Return the (IP, minute) pairs whose z-score is above the threshold."""
    now = now or datetime.now(timezone.utc)
    if len(counts) < min_samples:  # not enough history to know what is normal
        return []
    values = [c for _, _, c in counts]
    mean = statistics.fmean(values)
    std = statistics.pstdev(values)
    if std == 0:
        return []
    alerts = []
    for minute, ip, x in counts:
        z = (x - mean) / std
        recent = minute >= now - timedelta(minutes=recent_minutes)
        if z > threshold and x >= min_requests and recent:
            alerts.append(
                {
                    "@timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "minute": minute.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "client_ip": ip,
                    "requests_per_min": x,
                    "z_score": round(z, 2),
                    "mean": round(mean, 2),
                    "std": round(std, 2),
                }
            )
    return alerts


def alert_id(alert: dict) -> str:
    return f"{alert['client_ip']}_{alert['minute']}"


def ensure_index(client: httpx.Client, es: str) -> None:
    if client.head(f"{es}/{ALERT_INDEX}").status_code == 404:
        client.put(f"{es}/{ALERT_INDEX}", json=ALERT_MAPPING).raise_for_status()


def save_alert(client: httpx.Client, es: str, alert: dict) -> bool:
    """Write the alert; one document per (IP, minute). True when it is new."""
    r = client.put(
        f"{es}/{ALERT_INDEX}/_doc/{alert_id(alert)}", params={"refresh": "true"}, json=alert
    )
    r.raise_for_status()
    return r.json().get("result") == "created"


def describe_error(exc: httpx.HTTPError) -> str:
    """A message that says WHY Elasticsearch refused, instead of only the exception name."""
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text[:300].replace("\n", " ")
        hint = ""
        if "text" in body or "fielddata" in body:
            hint = (
                " -> the log index has the wrong field types. Run: python elk/setup_elk.py --check"
            )
        return f"Elasticsearch answered HTTP {exc.response.status_code}: {body}{hint}"
    return f"Elasticsearch not reachable ({exc.__class__.__name__}), will retry"


def check_once(client: httpx.Client, es: str, args) -> list[dict]:
    counts = fetch_counts(client, es, args.window)
    alerts = find_alerts(counts, args.threshold, args.min_requests, args.min_samples)
    new = []
    for a in alerts:
        if save_alert(client, es, a):
            new.append(a)
            print(
                f"[ALERT] {a['@timestamp']}  ip={a['client_ip']}"
                f"  requests/min={a['requests_per_min']}"
                f"  z={a['z_score']} (mean={a['mean']}, std={a['std']})"
            )
    return new


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--es", default=os.getenv("ES_LOGS_URL", "http://localhost:9201"))
    ap.add_argument("--window", type=int, default=30, help="minutes of history")
    ap.add_argument("--threshold", type=float, default=3.0)
    ap.add_argument("--min-requests", type=int, default=20)
    ap.add_argument("--min-samples", type=int, default=10)
    ap.add_argument("--interval", type=int, default=20, help="seconds between two checks")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    with httpx.Client(timeout=15) as client:
        ensure_index(client, args.es)
        print(
            f"Watching {args.es} (z > {args.threshold}, every {args.interval} s). Ctrl+C to stop."
        )
        while True:
            try:
                n = len(check_once(client, args.es, args))
                print(f"{datetime.now():%H:%M:%S} checked, {n} new alert(s)")
            except httpx.HTTPError as exc:
                print(describe_error(exc))
            if args.once:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
