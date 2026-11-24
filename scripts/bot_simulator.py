"""Simulate normal visitors, then a bot that sends a burst from one IP (task B7, owner: B).

Start `python scripts/zscore_alert.py` in another terminal, then run:
    python scripts/bot_simulator.py
Phase 1: normal traffic from 25 IPs (about 45 s). Phase 2: --burst-requests requests from ONE
fake IP as fast as possible. Phase 3: a little normal traffic. The alert should appear
within about 2 minutes. The fake IP is sent in the header X-Forwarded-For.
Only stack B endpoints are used, unless you pass --all-endpoints. A slow or failed request
never stops the script.
"""

import argparse
import random
import time

import httpx

NORMAL_IPS = [f"198.51.100.{i}" for i in range(1, 26)]
B_PATHS = [
    "/health", "/health", "/health", "/graph/influence/top?n=5",
    "/graph/neighbors/a_virgil", "/monitoring/alerts", "/does-not-exist",
]  # fmt: skip
OTHER_PATHS = ["/catalog/genres", "/search?q=republic", "/popular", "/events/work/w_0003"]
PATHS = B_PATHS  # kept for compatibility


def normal_traffic(client, n, ips, pause=0.3, rng=None, sleep=time.sleep, paths=None) -> int:
    rng = rng or random.Random()
    paths = paths or B_PATHS
    for i in range(1, n + 1):
        try:
            client.get(rng.choice(paths), headers={"X-Forwarded-For": rng.choice(ips)})
        except httpx.HTTPError:
            pass  # a slow request is still logged by the API: carry on
        if i % 50 == 0:
            print(f"  {i}/{n} ...", flush=True)
        sleep(pause)
    return n


def burst(client, ip, n, path="/health") -> int:
    for _ in range(n):
        try:
            client.get(path, headers={"X-Forwarded-For": ip})
        except httpx.HTTPError:
            pass
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--normal-requests", type=int, default=150)
    ap.add_argument("--pause", type=float, default=0.3)
    ap.add_argument("--timeout", type=float, default=3)
    ap.add_argument("--burst-ip", default="203.0.113.50")
    ap.add_argument("--burst-requests", type=int, default=300)
    ap.add_argument("--after-requests", type=int, default=40)
    ap.add_argument("--all-endpoints", action="store_true")
    args = ap.parse_args()
    paths = B_PATHS + (OTHER_PATHS if args.all_endpoints else [])

    with httpx.Client(base_url=args.api, timeout=args.timeout) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError:
            raise SystemExit(f"API not reachable at {args.api}. Start uvicorn first.")
        print(f"Phase 1: {args.normal_requests} normal requests from {len(NORMAL_IPS)} IPs ...")
        normal_traffic(client, args.normal_requests, NORMAL_IPS, args.pause, paths=paths)
        print(f"Phase 2: burst of {args.burst_requests} requests from {args.burst_ip} ...")
        start = time.time()
        burst(client, args.burst_ip, args.burst_requests)
        print(f"  done in {time.time() - start:.1f} s")
        print(f"Phase 3: {args.after_requests} normal requests ...")
        normal_traffic(client, args.after_requests, NORMAL_IPS, args.pause, paths=paths)
    print("Finished. Watch the terminal of zscore_alert.py and Kibana (requests per minute).")


if __name__ == "__main__":
    main()
