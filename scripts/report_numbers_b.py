"""Print the numbers of member B for the report (sections 4 to 6), as Markdown.

Start stack B and the API, then from the repo root:
    python scripts/report_numbers_b.py
    python scripts/report_numbers_b.py --cassandra-count    # also counts the events (slow)
Copy what it prints into docs/b_rapport_sections_4-6.md, in place of the [A REMPLIR] marks.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from backend.app.config import settings  # noqa: E402


def neo4j_numbers() -> list[str]:
    driver = GraphDatabase.driver(
        settings.neo4j_url, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    with driver.session() as s:
        labels = {
            r["l"]: r["n"]
            for r in s.run("MATCH (n) WHERE NOT n:BNode RETURN labels(n)[0] AS l, count(*) AS n")
        }
        rels = {
            r["t"]: r["n"]
            for r in s.run(
                "MATCH ()-[r]->() WHERE type(r) <> 'BLINK' RETURN type(r) AS t, count(*) AS n"
            )
        }
        origins = {
            r["o"]: r["n"]
            for r in s.run(
                "MATCH ()-[r:INFLUENCED_BY|STUDENT_OF]->() "
                "RETURN coalesce(r.origin, 'unknown') AS o, count(*) AS n"
            )
        }
        external = s.run("MATCH (a:Author {external: true}) RETURN count(a) AS n").single()["n"]
    driver.close()
    links = rels.get("INFLUENCED_BY", 0) + rels.get("STUDENT_OF", 0)
    return [
        "## Neo4j",
        f"- Authors: {labels.get('Author', 0)} ({external} external), "
        f"works: {labels.get('Work', 0)}, genres: {labels.get('Genre', 0)}",
        f"- Influence links: {links} (INFLUENCED_BY {rels.get('INFLUENCED_BY', 0)}, "
        f"STUDENT_OF {rels.get('STUDENT_OF', 0)})",
        "- Origin of the links: " + ", ".join(f"{o} {n}" for o, n in sorted(origins.items())),
    ]


def api_numbers(api: str) -> list[str]:
    lines = ["## PageRank (top 5, API)"]
    top = httpx.get(f"{api}/graph/influence/top", params={"n": 5}, timeout=30).json()
    lines += [f"- {i}. {a['name']}: {a['score']}" for i, a in enumerate(top, 1)]
    alerts = httpx.get(f"{api}/monitoring/alerts", params={"limit": 200}, timeout=30).json()
    lines += ["## Alerts", f"- Alerts stored: {len(alerts)}"]
    for a in alerts[:3]:
        lines.append(
            f"- {a['ts']}: {a['client_ip']}, {a['requests_per_min']} requests/min, "
            f"z = {a['z_score']}"
        )
    return lines


def elk_numbers() -> list[str]:
    count = httpx.get(f"{settings.es_logs_url}/pinakes-logs-*/_count", timeout=30).json()["count"]
    return ["## ELK", f"- Request logs indexed in Elasticsearch: {count}"]


def cassandra_numbers() -> list[str]:
    from cassandra.cluster import Cluster

    session = Cluster([h.strip() for h in settings.cassandra_hosts.split(",")]).connect()
    n = session.execute("SELECT COUNT(*) FROM pinakes.reads_by_user", timeout=300).one()[0]
    return ["## Cassandra", f"- Events in reads_by_user: {n}"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--cassandra-count", action="store_true")
    args = ap.parse_args()
    parts = [("Neo4j", neo4j_numbers), ("API", lambda: api_numbers(args.api)), ("ELK", elk_numbers)]
    if args.cassandra_count:
        parts.append(("Cassandra", cassandra_numbers))
    for name, fn in parts:
        try:
            print("\n".join(fn()) + "\n")
        except Exception as exc:  # one service off must not hide the others
            print(f"## {name}\n- not available ({exc.__class__.__name__}: {exc})\n")


if __name__ == "__main__":
    main()
