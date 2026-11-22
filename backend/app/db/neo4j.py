"""Neo4j access and graph queries (owner: B). Used by routers/graph.py."""

from functools import lru_cache

from neo4j import GraphDatabase

from backend.app.config import settings

REL_TYPES = "INFLUENCED_BY|STUDENT_OF"
MAX_PATH_LENGTH = 8  # longest path searched between two authors
MAX_DEPTH = 4  # largest depth accepted by /graph/neighbors
MAX_EDGES = 500  # safety limit for /graph/neighbors

Q_PATH = """
MATCH (a:Author {id: $a}), (b:Author {id: $b})
MATCH p = shortestPath((a)-[:__REL__*..__MAXLEN__]-(b))
RETURN [n IN nodes(p) | {id: n.id, name: n.name}] AS nodes,
       [r IN relationships(p) |
          {source: startNode(r).id, target: endNode(r).id, type: type(r)}] AS edges
"""
Q_NEIGHBORS = """
MATCH p = (a:Author {id: $id})-[:__REL__*1..__DEPTH__]-(:Author)
UNWIND relationships(p) AS r
WITH DISTINCT r
RETURN startNode(r).id AS s, startNode(r).name AS sn,
       endNode(r).id AS t, endNode(r).name AS tn, type(r) AS type
LIMIT __LIMIT__
"""


@lru_cache(maxsize=1)
def get_driver():
    return GraphDatabase.driver(
        settings.neo4j_url, auth=(settings.neo4j_user, settings.neo4j_password)
    )


def run(query: str, **params) -> list[dict]:
    with get_driver().session() as session:
        return [record.data() for record in session.run(query, **params)]


def existing_author_ids(ids: list[str]) -> set[str]:
    rows = run("MATCH (a:Author) WHERE a.id IN $ids RETURN a.id AS id", ids=list(ids))
    return {r["id"] for r in rows}


def get_author(author_id: str) -> dict | None:
    rows = run("MATCH (a:Author {id: $id}) RETURN a.id AS id, a.name AS name", id=author_id)
    return rows[0] if rows else None


def shortest_path(source: str, target: str) -> dict:
    """Shortest path between two authors, ignoring the direction of the links."""
    if source == target:
        return {"found": True, "length": 0, "nodes": [get_author(source)], "edges": []}
    query = Q_PATH.replace("__REL__", REL_TYPES).replace("__MAXLEN__", str(MAX_PATH_LENGTH))
    rows = run(query, a=source, b=target)
    if not rows:
        return {"found": False, "length": None, "nodes": [], "edges": []}
    row = rows[0]
    return {
        "found": True,
        "length": len(row["edges"]),
        "nodes": row["nodes"],
        "edges": row["edges"],
    }


def neighbors(author_id: str, depth: int = 2) -> dict:
    depth = max(1, min(int(depth), MAX_DEPTH))
    center = get_author(author_id)
    nodes = {center["id"]: center} if center else {}
    query = (
        Q_NEIGHBORS.replace("__REL__", REL_TYPES)
        .replace("__DEPTH__", str(depth))
        .replace("__LIMIT__", str(MAX_EDGES))
    )
    edges = []
    for r in run(query, id=author_id):
        nodes.setdefault(r["s"], {"id": r["s"], "name": r["sn"]})
        nodes.setdefault(r["t"], {"id": r["t"], "name": r["tn"]})
        edges.append({"source": r["s"], "target": r["t"], "type": r["type"]})
    return {"nodes": list(nodes.values()), "edges": edges}


def pagerank(nodes, edges, damping: float = 0.85, iterations: int = 100, tol: float = 1e-10):
    """PR(v) = (1-d)/N + d * sum over u->v of PR(u)/L(u), with L(u) = number of links of u.

    `edges` are (source, target) pairs: source points to target. Our links point from the
    influenced author to the influencer, so the best score goes to the most influential
    author. Authors without outgoing links share their score with everyone (standard fix).
    """
    nodes = sorted(set(nodes) | {x for e in edges for x in e})
    n = len(nodes)
    if n == 0:
        return {}
    out = {v: set() for v in nodes}
    for s, t in edges:
        if s != t:
            out[s].add(t)
    pr = {v: 1.0 / n for v in nodes}
    for _ in range(iterations):
        dangling = sum(pr[v] for v in nodes if not out[v])
        new = {v: (1 - damping) / n + damping * dangling / n for v in nodes}
        for v in nodes:
            for t in out[v]:
                new[t] += damping * pr[v] / len(out[v])
        diff = sum(abs(new[v] - pr[v]) for v in nodes)
        pr = new
        if diff < tol:
            break
    return pr


def top_influence(n: int = 10) -> list[dict]:
    authors = run("MATCH (a:Author) RETURN a.id AS id, a.name AS name")
    links = run(f"MATCH (a:Author)-[:{REL_TYPES}]->(b:Author) RETURN DISTINCT a.id AS s, b.id AS t")
    names = {a["id"]: a["name"] for a in authors}
    scores = pagerank(names.keys(), [(r["s"], r["t"]) for r in links])
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], names.get(kv[0], "")))
    return [{"author_id": i, "name": names.get(i, i), "score": round(s, 6)} for i, s in ranked[:n]]
