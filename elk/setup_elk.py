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


EXPECTED_TYPES = {
    "@timestamp": "date",
    "client_ip": "ip",
    "method": "keyword",
    "path": "keyword",
    "status": "integer",
    "latency_ms": "float",
    "geoip.location": "geo_point",
}


def field_types(client: httpx.Client, es: str) -> dict[str, dict[str, str | None]]:
    """{index: {field: type, or None when the field is absent}} for every log index."""
    r = client.get(f"{es}/pinakes-logs-*/_mapping/field/{','.join(EXPECTED_TYPES)}")
    r.raise_for_status()
    result: dict[str, dict[str, str | None]] = {}
    for index, body in r.json().items():
        mappings = body.get("mappings", {})
        types: dict[str, str | None] = {}
        for field in EXPECTED_TYPES:
            info = mappings.get(field)
            types[field] = next(iter(info["mapping"].values()))["type"] if info else None
        result[index] = types
    return result


def check_mapping(client: httpx.Client, es: str) -> list[tuple]:
    """Problems as (level, index, field, expected, actual). geoip.location may be absent
    (no public IP yet): that is only a warning."""
    problems = []
    for index, types in sorted(field_types(client, es).items()):
        for field, expected in EXPECTED_TYPES.items():
            actual = types[field]
            if actual == expected:
                continue
            level = "WARN" if field == "geoip.location" and actual is None else "FAIL"
            problems.append((level, index, field, expected, actual))
    return problems


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


def run_check(es: str) -> int:
    with httpx.Client(timeout=30) as client:
        wait_for(client, es, "Elasticsearch (logs)")
        problems = check_mapping(client, es)
        indices = list(field_types(client, es))
    if not indices:
        print("[WARN] no log index yet: start the API, send traffic, wait 30 s, run this again.")
        return 0
    print(f"Log indices: {', '.join(indices)}")
    for level, index, field, expected, actual in problems:
        print(f"[{level}] {index}: field '{field}' is {actual or 'missing'}, expected {expected}")
    fails = [p for p in problems if p[0] == "FAIL"]
    if fails:
        print("\nThe index was created before the index template: Elasticsearch guessed the types.")
        print("Fix: python elk/setup_elk.py --reset")
        print("     (deletes the log indices and installs the template)")
        print("Then send traffic again, and refresh the Kibana data view (see the guide).")
        return 1
    print("[OK] the field types are the expected ones.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--es", default="http://localhost:9201")
    ap.add_argument("--kibana", default="http://localhost:5601")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--check", action="store_true", help="only check the types of the log fields")
    args = ap.parse_args()

    if args.check:
        sys.exit(run_check(args.es))

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
