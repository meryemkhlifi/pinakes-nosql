"""Alerts stored in Elasticsearch (logs) by scripts/zscore_alert.py (owner: B)."""

import httpx

from backend.app.config import settings

ALERT_INDEX = "pinakes-alerts"


def parse_alerts(response: dict) -> list[dict]:
    return [
        {
            "ts": hit["_source"]["@timestamp"],
            "client_ip": hit["_source"]["client_ip"],
            "requests_per_min": hit["_source"]["requests_per_min"],
            "z_score": hit["_source"]["z_score"],
        }
        for hit in response["hits"]["hits"]
    ]


def latest_alerts(limit: int = 20) -> list[dict]:
    body = {"size": limit, "sort": [{"@timestamp": "desc"}]}
    r = httpx.post(f"{settings.es_logs_url}/{ALERT_INDEX}/_search", json=body, timeout=5)
    if r.status_code == 404:  # the index does not exist yet: no alert so far
        return []
    r.raise_for_status()
    return parse_alerts(r.json())
