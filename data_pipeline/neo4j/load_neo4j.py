"""Load authors, works, genres and influence links into Neo4j (task B3, owner: B).

Run from the repo root, with stack B started:
    python -m data_pipeline.neo4j.load_neo4j
    python -m data_pipeline.neo4j.load_neo4j --works data/sample/works_sample.json --reset

Graph model:
    (Author)-[:WROTE]->(Work)-[:IN_GENRE]->(Genre)
    (Author)-[:INFLUENCED_BY]->(Author)   X was influenced by Y
    (Author)-[:STUDENT_OF]->(Author)      X was a student of Y
The script uses MERGE everywhere: you can run it again without creating duplicates.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError

from backend.app.config import settings

BATCH = 500
INFLUENCE_TYPES = ("INFLUENCED_BY", "STUDENT_OF")

CONSTRAINTS = [
    "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (a:Author) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT work_id IF NOT EXISTS FOR (w:Work) REQUIRE w.id IS UNIQUE",
    "CREATE CONSTRAINT genre_name IF NOT EXISTS FOR (g:Genre) REQUIRE g.name IS UNIQUE",
]
Q_AUTHORS = """
UNWIND $rows AS row
MERGE (a:Author {id: row.id})
SET a.name = row.name, a.birth_year = row.birth_year, a.bio = row.bio, a.external = row.external
"""
Q_WORKS = """
UNWIND $rows AS row
MERGE (w:Work {id: row.id})
SET w.title = row.title, w.year = row.year, w.language = row.language
MERGE (g:Genre {name: row.genre})
MERGE (w)-[:IN_GENRE]->(g)
WITH w, row
UNWIND row.author_ids AS author_id
MATCH (a:Author {id: author_id})
MERGE (a)-[:WROTE]->(w)
"""
# A relationship type cannot be a parameter in Cypher, so we replace __TYPE__ (checked list only).
Q_LINKS = """
UNWIND $rows AS row
MATCH (a:Author {id: row.source}), (b:Author {id: row.target})
MERGE (a)-[r:__TYPE__]->(b)
SET r.origin = row.origin
"""


def read_works(path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_rows(works: list[dict]):
    """Works file -> (author rows, work rows). An author appears once, even with many works."""
    authors: dict[str, dict] = {}
    work_rows = []
    for w in works:
        ids = []
        for a in w["authors"]:
            cur = authors.setdefault(
                a["id"],
                {
                    "id": a["id"],
                    "name": a["name"],
                    "birth_year": None,
                    "bio": None,
                    "external": False,
                },
            )
            if cur["birth_year"] is None and a.get("birth_year") is not None:
                cur["birth_year"] = a["birth_year"]
            if not cur["bio"] and a.get("bio"):
                cur["bio"] = a["bio"]
            ids.append(a["id"])
        work_rows.append(
            {
                "id": w["_id"],
                "title": w["title"],
                "year": w.get("year"),
                "language": w.get("language"),
                "genre": w["genre"],
                "author_ids": ids,
            }
        )
    return list(authors.values()), work_rows


def read_influences(path, known_ids):
    """Influence file -> (external author rows, edge rows per type, number of skipped edges)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    known = set(known_ids)
    external = []
    for a in data.get("external_authors", []):
        if a["id"] not in known:
            known.add(a["id"])
            external.append(
                {
                    "id": a["id"],
                    "name": a["name"],
                    "birth_year": a.get("birth_year"),
                    "bio": None,
                    "external": True,
                }
            )
    by_type = {t: [] for t in INFLUENCE_TYPES}
    skipped = 0
    for e in data.get("edges", []):
        ok = (
            e.get("type") in by_type
            and e["source"] in known
            and e["target"] in known
            and e["source"] != e["target"]
        )
        if not ok:
            skipped += 1
            continue
        by_type[e["type"]].append(
            {"source": e["source"], "target": e["target"], "origin": e.get("origin", "unknown")}
        )
    return external, by_type, skipped


def batched(rows, size=BATCH):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def connect(retries=10, delay=3):
    driver = GraphDatabase.driver(
        settings.neo4j_url, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    for attempt in range(1, retries + 1):
        try:
            driver.verify_connectivity()
            return driver
        except AuthError:
            sys.exit(
                "Neo4j refused the password. Neo4j keeps the password of its FIRST start.\n"
                "If you changed NEO4J_PASSWORD in .env since then, either put the old one back,\n"
                "or reset the volume: docker compose -p pinakes-b -f docker/stack-b.yml down -v"
            )
        except Exception as exc:  # container still starting
            print(f"Neo4j not ready ({attempt}/{retries}): {exc.__class__.__name__}")
            time.sleep(delay)
    sys.exit("Cannot reach Neo4j. Check: docker compose -p pinakes-b -f docker/stack-b.yml ps")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--works", default="data/sample/works_sample.json")
    ap.add_argument("--influences", default="data/sample/influences.json")
    ap.add_argument("--reset", action="store_true", help="delete everything in Neo4j first")
    args = ap.parse_args()

    authors, work_rows = build_rows(read_works(args.works))
    external, by_type, skipped = [], {t: [] for t in INFLUENCE_TYPES}, 0
    if Path(args.influences).exists():
        external, by_type, skipped = read_influences(args.influences, [a["id"] for a in authors])
    else:
        print(f"No {args.influences}: loading works only (run generate_influences first).")

    driver = connect()
    with driver.session() as session:
        if args.reset:
            session.run("MATCH (n) DETACH DELETE n").consume()
            print("Database emptied.")
        for q in CONSTRAINTS:
            session.run(q).consume()
        for batch in batched(authors + external):
            session.run(Q_AUTHORS, rows=batch).consume()
        for batch in batched(work_rows):
            session.run(Q_WORKS, rows=batch).consume()
        for edge_type, rows in by_type.items():
            for batch in batched(rows):
                session.run(Q_LINKS.replace("__TYPE__", edge_type), rows=batch).consume()
        nodes = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label"
        ).data()
        rels = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY type"
        ).data()
    driver.close()

    print("Nodes:", {r["label"]: r["n"] for r in nodes})
    print("Links:", {r["type"]: r["n"] for r in rels})
    if skipped:
        print(f"{skipped} influence links skipped (unknown author or wrong type).")


if __name__ == "__main__":
    main()
