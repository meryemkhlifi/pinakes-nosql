"""Prepare Elasticsearch (logs) and Kibana for the API logs (task B6, owner: B).

Run once, after stack B is up and BEFORE the first logs arrive:
    python elk/setup_elk.py
    python elk/setup_elk.py --reset      # also delete the pinakes-logs-* indices of tests
What it does: (1) installs the index template `pinakes-logs` (types: ip, integer, float,
geo_point...), (2) creates the Kibana data view `pinakes-logs-*` on @timestamp.
"""

import argparse
import sys
import time

import httpx

TEMPLATE_NAME = "pinakes-logs"
DATA_VIEW_ID = "pinakes-logs"


def build_template() -> dict:
    return {
        "index_patterns": ["pinakes-logs-*"],
        "priority": 200,
        "template": {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "properties": {
                    "@timestamp": {"type": "date"},
                    "client_ip": {"type": "ip", "ignore_malformed": True},
                    "method": {"type": "keyword"},
                    "path": {"type": "keyword"},
                    "status": {"type": "integer"},
                    "latency_ms": {"type": "float"},
                    "user_agent": {"type": "keyword", "ignore_above": 512},
                    "geoip": {"properties": {"location": {"type": "geo_point"}}},
                }
            },
        },
    }


def build_data_view() -> dict:
    return {
        "data_view": {
            "id": DATA_VIEW_ID,
            "title": "pinakes-logs-*",
            "name": "Pinakes API logs",
            "timeFieldName": "@timestamp",
        },
        "override": True,
    }


def wait_for(client: httpx.Client, url: str, name: str, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if client.get(url).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        print(f"  waiting for {name} ...")
        time.sleep(5)
    sys.exit(f"{name} is not ready after {timeout} s. Check: docker compose ... ps")


def delete_log_indices(client: httpx.Client, es: str) -> list[str]:
    # Elasticsearch 8 refuses wildcard deletes, so delete each index by name.
    rows = client.get(f"{es}/_cat/indices/pinakes-logs-*", params={"format": "json"}).json()
    names = [r["index"] for r in rows]
    for name in names:
        client.delete(f"{es}/{name}").raise_for_status()
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--es", default="http://localhost:9201")
    ap.add_argument("--kibana", default="http://localhost:5601")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    with httpx.Client(timeout=30) as client:
        wait_for(client, args.es, "Elasticsearch (logs)")
        if args.reset:
            print("Deleted indices:", delete_log_indices(client, args.es) or "none")
        r = client.put(f"{args.es}/_index_template/{TEMPLATE_NAME}", json=build_template())
        r.raise_for_status()
        print(f"Index template '{TEMPLATE_NAME}' installed.")

        wait_for(client, f"{args.kibana}/api/status", "Kibana")
        r = client.post(
            f"{args.kibana}/api/data_views/data_view",
            json=build_data_view(),
            headers={"kbn-xsrf": "true"},
        )
        r.raise_for_status()
        print("Kibana data view 'pinakes-logs-*' created. Open Discover to see the requests.")


if __name__ == "__main__":
    main()
