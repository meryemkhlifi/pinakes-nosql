"""Day 2 check for member B. Run from the repo root:
    python scripts/check_day2_b.py [--from a_horace --to a_homer]
It reads Neo4j directly, then (if the API is running) calls the three graph endpoints.
"""

import argparse
import sys

import httpx
from neo4j import GraphDatabase

from backend.app.config import settings

ap = argparse.ArgumentParser()
ap.add_argument("--from", dest="source", default="a_horace")
ap.add_argument("--to", dest="target", default="a_homer")
ap.add_argument("--api", default="http://localhost:8000")
args = ap.parse_args()
problems = []


def check(ok: bool, text: str):
    print(("[OK]   " if ok else "[FAIL] ") + text)
    if not ok:
        problems.append(text)


try:
    driver = GraphDatabase.driver(
        settings.neo4j_url, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    with driver.session() as s:
        nodes = {r["l"]: r["n"] for r in s.run("MATCH (n) RETURN labels(n)[0] AS l, count(*) AS n")}
        rels = {
            r["t"]: r["n"] for r in s.run("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n")
        }
        path = s.run(
            "MATCH (a:Author {id: $a}), (b:Author {id: $b}) "
            "MATCH p = shortestPath((a)-[:INFLUENCED_BY|STUDENT_OF*..8]-(b)) RETURN length(p) AS n",
            a=args.source,
            b=args.target,
        ).single()
    check(nodes.get("Author", 0) > 0, f"Authors in Neo4j: {nodes.get('Author', 0)}")
    check(nodes.get("Work", 0) > 0, f"Works in Neo4j: {nodes.get('Work', 0)}")
    check(nodes.get("Genre", 0) > 0, f"Genres in Neo4j: {nodes.get('Genre', 0)}")
    n_links = rels.get("INFLUENCED_BY", 0) + rels.get("STUDENT_OF", 0)
    check(n_links > 0, f"Influence links: {n_links}")
    check(path is not None, f"Path {args.source} -> {args.target}: {path['n'] if path else 'none'}")
except Exception as exc:
    check(False, f"Neo4j not reachable: {exc.__class__.__name__}: {exc}")

try:
    p = httpx.get(f"{args.api}/graph/path", params={"from": args.source, "to": args.target})
    check(p.status_code == 200 and p.json().get("found"), f"GET /graph/path -> {p.status_code}")
    q = httpx.get(f"{args.api}/graph/neighbors/{args.source}")
    check(q.status_code == 200, f"GET /graph/neighbors -> {q.status_code}")
    t = httpx.get(f"{args.api}/graph/influence/top", params={"n": 5})
    check(
        t.status_code == 200 and len(t.json()) > 0, f"GET /graph/influence/top -> {t.status_code}"
    )
    if t.status_code == 200:
        for row in t.json():
            print(f"         {row['score']:.4f}  {row['name']}")
except httpx.HTTPError:
    print("[skip] API not running (start it with: uvicorn backend.app.main:app --reload)")

sys.exit(1 if problems else 0)
