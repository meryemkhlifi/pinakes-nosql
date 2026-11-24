"""Send some varied requests to the API so that logs appear in Kibana (task B6, owner: B).

    python scripts/smoke_traffic.py            # 200 requests, only stack B endpoints
    python scripts/smoke_traffic.py --n 500 --pause 0.02
    python scripts/smoke_traffic.py --all-endpoints    # also MongoDB / Elasticsearch / Redis ones
Each request gets a fake client IP (header X-Forwarded-For) from several countries, so the
map and the 'top IPs' panel have data. Slow or failed requests never stop the script.
"""

import argparse
import random
import time
from collections import Counter

import httpx

IPS = [
    "8.8.8.8", "1.1.1.1", "9.9.9.9", "208.67.222.222", "77.88.8.8", "80.67.169.12",
    "114.114.114.114", "193.0.14.129", "196.200.176.1", "200.221.11.100",
]  # fmt: skip
# Endpoints that only need stack B (Neo4j, Elasticsearch logs). Some give 404 or 422 on purpose.
B_PATHS = [
    "/health", "/health", "/health", "/graph/influence/top?n=5",
    "/graph/path?from=a_horace&to=a_homer", "/graph/neighbors/a_virgil",
    "/graph/neighbors/a_nobody", "/graph/path?from=a_horace", "/monitoring/alerts",
    "/does-not-exist",
]  # fmt: skip
# Endpoints that need stack A (MongoDB, Elasticsearch catalog, Redis) or Cassandra.
OTHER_PATHS = [
    "/catalog/genres", "/search?q=republic", "/popular", "/events/work/w_0003",
    "/events/user/u_1",
]  # fmt: skip


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--pause", type=float, default=0.05, help="seconds between requests")
    ap.add_argument("--timeout", type=float, default=3, help="seconds to wait for one request")
    ap.add_argument("--all-endpoints", action="store_true")
    args = ap.parse_args()

    paths = B_PATHS + (OTHER_PATHS if args.all_endpoints else [])
    rng = random.Random()
    statuses: Counter = Counter()
    with httpx.Client(base_url=args.api, timeout=args.timeout) as client:
        for i in range(1, args.n + 1):
            headers = {"X-Forwarded-For": rng.choice(IPS)}
            try:
                if args.all_endpoints and rng.random() < 0.2:
                    body = {
                        "work_id": f"w_{rng.randint(1, 20):04d}",
                        "user_id": f"u_{rng.randint(1, 50)}",
                    }
                    r = client.post("/events/read", json=body, headers=headers)
                else:
                    r = client.get(rng.choice(paths), headers=headers)
                statuses[r.status_code] += 1
            except httpx.HTTPError as exc:
                statuses[exc.__class__.__name__] += 1
            if i % 50 == 0:
                print(f"  {i}/{args.n} requests sent ...", flush=True)
            time.sleep(args.pause)
    print(f"{args.n} requests sent. Status codes: {dict(statuses)}")
    print("Wait about 30 seconds, then open Kibana > Discover (last 15 minutes).")


if __name__ == "__main__":
    main()
