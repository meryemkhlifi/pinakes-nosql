"""Send some varied requests to the API so that logs appear in Kibana (task B6, owner: B).

    python scripts/smoke_traffic.py            # 200 requests
    python scripts/smoke_traffic.py --n 500 --pause 0.02
Each request gets a fake client IP (header X-Forwarded-For) from several countries, so the
map and the 'top IPs' panel of Day 4 have data. Not the bot of Day 4 (bot_simulator.py).
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
GET_PATHS = [
    "/health", "/health", "/health",
    "/catalog/genres", "/search?q=republic", "/graph/influence/top?n=5",
    "/graph/path?from=a_horace&to=a_homer", "/graph/neighbors/a_virgil",
    "/events/work/w_0003", "/events/user/u_1", "/monitoring/alerts", "/popular",
    "/does-not-exist",
]  # fmt: skip


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--pause", type=float, default=0.05, help="seconds between requests")
    args = ap.parse_args()

    rng = random.Random()
    statuses: Counter = Counter()
    with httpx.Client(base_url=args.api, timeout=10) as client:
        for _ in range(args.n):
            headers = {"X-Forwarded-For": rng.choice(IPS)}
            try:
                if rng.random() < 0.2:
                    body = {
                        "work_id": f"w_{rng.randint(1, 20):04d}",
                        "user_id": f"u_{rng.randint(1, 50)}",
                    }
                    r = client.post("/events/read", json=body, headers=headers)
                else:
                    r = client.get(rng.choice(GET_PATHS), headers=headers)
                statuses[r.status_code] += 1
            except httpx.HTTPError as exc:
                statuses[exc.__class__.__name__] += 1
            time.sleep(args.pause)
    print(f"{args.n} requests sent. Status codes: {dict(statuses)}")
    print("Wait about 30 seconds, then open Kibana > Discover (last 15 minutes).")


if __name__ == "__main__":
    main()
