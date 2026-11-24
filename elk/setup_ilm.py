"""Delete the logs after 7 days (task B6, owner: B).

    python elk/setup_ilm.py
It creates the lifecycle policy `pinakes-logs-7d`, adds it to the index template (new daily
indices get it), and applies it to the indices that already exist. Elasticsearch checks the
policies every 10 minutes, so an index disappears 7 to 7.01 days after its creation.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from elk.setup_elk import TEMPLATE_NAME, build_template, wait_for  # noqa: E402

POLICY_NAME = "pinakes-logs-7d"


def build_policy(days: int = 7) -> dict:
    return {"policy": {"phases": {"delete": {"min_age": f"{days}d", "actions": {"delete": {}}}}}}


def template_with_policy() -> dict:
    template = build_template()
    template["template"]["settings"]["index.lifecycle.name"] = POLICY_NAME
    return template


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--es", default="http://localhost:9201")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    with httpx.Client(timeout=30) as client:
        wait_for(client, args.es, "Elasticsearch (logs)")
        client.put(
            f"{args.es}/_ilm/policy/{POLICY_NAME}", json=build_policy(args.days)
        ).raise_for_status()
        print(f"Policy '{POLICY_NAME}' created: delete after {args.days} days.")
        client.put(
            f"{args.es}/_index_template/{TEMPLATE_NAME}", json=template_with_policy()
        ).raise_for_status()
        print("Index template updated: new daily indices use the policy.")
        r = client.put(
            f"{args.es}/pinakes-logs-*/_settings", json={"index.lifecycle.name": POLICY_NAME}
        )
        print("Existing indices:", "policy applied." if r.status_code == 200 else r.text[:200])


if __name__ == "__main__":
    main()
