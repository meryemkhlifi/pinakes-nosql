"""Graph data for the benchmark: the real influence graph or a bigger synthetic one (owner: B)."""

import random
from collections import deque


def edge_set(edges) -> list[tuple[str, str]]:
    """Undirected, without loops and duplicates: (a, b) with a < b."""
    return sorted({tuple(sorted(e)) for e in edges if e[0] != e[1]})


def synthetic_graph(nodes: int, edges_per_node: int = 2, seed: int = 42):
    """Random connected graph: a spanning tree plus random links (degree ~ 2 x edges_per_node)."""
    rng = random.Random(seed)
    ids = [f"n{i:06d}" for i in range(nodes)]
    edges = [(ids[i], ids[rng.randrange(i)]) for i in range(1, nodes)]  # tree: connected
    for _ in range(nodes * (edges_per_node - 1)):
        edges.append((rng.choice(ids), rng.choice(ids)))
    return ids, edge_set(edges)


def read_neo4j_graph(driver):
    """The real influence graph of the project (Author nodes and their influence links)."""
    with driver.session() as session:
        nodes = [r["id"] for r in session.run("MATCH (a:Author) RETURN a.id AS id")]
        rows = session.run(
            "MATCH (a:Author)-[:INFLUENCED_BY|STUDENT_OF]->(b:Author) RETURN a.id AS a, b.id AS b"
        )
        edges = [(r["a"], r["b"]) for r in rows]
    return sorted(nodes), edge_set(edges)


def adjacency(edges) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    return adj


def bfs_distances(adj: dict[str, list[str]], source: str, max_depth: int) -> dict[str, int]:
    dist = {source: 0}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        if dist[node] == max_depth:
            continue
        for nxt in adj.get(node, ()):
            if nxt not in dist:
                dist[nxt] = dist[node] + 1
                queue.append(nxt)
    return dist


def pairs_by_depth(adj, depths, per_depth: int = 10, seed: int = 7, max_sources: int = 2000):
    """{depth: [(source, target), ...]}: pairs whose shortest path has exactly `depth` links."""
    rng = random.Random(seed)
    sources = sorted(adj)
    rng.shuffle(sources)
    found: dict[int, list[tuple[str, str]]] = {d: [] for d in depths}
    top = max(depths)
    for source in sources[:max_sources]:
        dist = bfs_distances(adj, source, top)
        for d in depths:
            if len(found[d]) < per_depth:
                targets = sorted(n for n, k in dist.items() if k == d)
                if targets:
                    found[d].append((source, rng.choice(targets)))
        if all(len(v) >= per_depth for v in found.values()):
            break
    return {d: pairs for d, pairs in found.items() if pairs}
