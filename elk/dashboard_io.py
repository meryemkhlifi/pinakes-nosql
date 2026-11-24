"""Export / import the Kibana dashboard (task B6, owner: B).

After building the dashboard in Kibana (see docs/b_dashboard_guide.md):
    python elk/dashboard_io.py export     # writes elk/dashboard.ndjson, then git add it
On another laptop (or after a reset), to get the same dashboard back:
    python elk/dashboard_io.py import
"""

import argparse
import sys
from pathlib import Path

import httpx

FILE = Path(__file__).with_name("dashboard.ndjson")
HEADERS = {"kbn-xsrf": "true"}


def export_dashboard(client: httpx.Client, kibana: str) -> str:
    r = client.post(
        f"{kibana}/api/saved_objects/_export",
        json={"type": ["dashboard"], "includeReferencesDeep": True, "excludeExportDetails": True},
        headers=HEADERS,
    )
    r.raise_for_status()
    return r.text


def import_dashboard(client: httpx.Client, kibana: str, content: bytes) -> dict:
    r = client.post(
        f"{kibana}/api/saved_objects/_import",
        params={"overwrite": "true"},
        files={"file": ("dashboard.ndjson", content, "application/ndjson")},
        headers=HEADERS,
    )
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("action", choices=["export", "import"])
    ap.add_argument("--kibana", default="http://localhost:5601")
    ap.add_argument("--file", default=str(FILE))
    args = ap.parse_args()

    with httpx.Client(timeout=60) as client:
        if args.action == "export":
            text = export_dashboard(client, args.kibana)
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if not any('"type":"dashboard"' in ln for ln in lines):
                sys.exit(
                    "No dashboard found in Kibana. Build and save it first (Dashboard > Save)."
                )
            Path(args.file).write_text(
                text if text.endswith("\n") else text + "\n", encoding="utf-8"
            )
            print(f"{len(lines)} saved objects written to {args.file}")
        else:
            result = import_dashboard(client, args.kibana, Path(args.file).read_bytes())
            print(
                "Imported:",
                result.get("successCount", 0),
                "objects. Success:",
                result.get("success"),
            )


if __name__ == "__main__":
    main()
