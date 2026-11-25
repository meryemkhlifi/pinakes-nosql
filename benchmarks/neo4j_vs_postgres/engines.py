"""The two engines of the benchmark: Neo4j (shortestPath) and PostgreSQL (recursive query).

Both work on a COPY of the graph (label BNode / table bench_adj), so the real graph of the
project is never touched. Links are undirected for both.
"""

import psycopg
from psycopg import errors

BATCH = 5000

PG_QUERY = """
WITH RECURSIVE walk(node, depth, path) AS (
    SELECT %(src)s::text, 0, ARRAY[%(src)s::text]
  UNION ALL
    SELECT a.b, w.depth + 1, w.path || a.b
    FROM walk w JOIN bench_adj a ON a.a = w.node
    WHERE w.depth < %(maxd)s AND NOT (a.b = ANY(w.path))
)
SELECT depth FROM walk WHERE node = %(dst)s LIMIT 1
"""
NEO_PATH = """
MATCH (a:BNode {id: $src}), (b:BNode {id: $dst})
MATCH p = shortestPath((a)-[:BLINK*..__D__]-(b))
RETURN length(p) AS d
"""


class PgEngine:
    name = "PostgreSQL"

    def __init__(self, url: str, timeout_ms: int = 20000):
        self.conn = psycopg.connect(url, autocommit=True)
        self.timeout_ms = timeout_ms
        self.timeouts = 0
        self.conn.execute(f"SET statement_timeout = {int(timeout_ms)}")

    def load(self, edges) -> None:
        c = self.conn
        c.execute("DROP TABLE IF EXISTS bench_adj")
        c.execute("CREATE TABLE bench_adj (a text NOT NULL, b text NOT NULL)")
        with c.cursor() as cur, cur.copy("COPY bench_adj (a, b) FROM STDIN") as copy:
            for a, b in edges:  # one row per direction: the graph is undirected
                copy.write_row((a, b))
                copy.write_row((b, a))
        c.execute("CREATE INDEX bench_adj_a ON bench_adj (a)")
        c.execute("ANALYZE bench_adj")

    def shortest(self, src: str, dst: str, depth: int):
        """Number of links of the shortest path (None if there is none within `depth`)."""
        try:
            row = self.conn.execute(PG_QUERY, {"src": src, "dst": dst, "maxd": depth}).fetchone()
        except errors.QueryCanceled:
            self.timeouts += 1
            return "timeout"
        return row[0] if row else None

    def close(self) -> None:
        self.conn.close()


class NeoEngine:
    name = "Neo4j"

    def __init__(self, driver):
        self.driver = driver

    def load(self, nodes, edges) -> None:
        with self.driver.session() as s:
            s.run("MATCH (n:BNode) DETACH DELETE n").consume()
            s.run(
                "CREATE CONSTRAINT bnode_id IF NOT EXISTS FOR (n:BNode) REQUIRE n.id IS UNIQUE"
            ).consume()
            for i in range(0, len(nodes), BATCH):
                s.run(
                    "UNWIND $ids AS id CREATE (:BNode {id: id})", ids=nodes[i : i + BATCH]
                ).consume()
            for i in range(0, len(edges), BATCH):
                rows = [{"a": a, "b": b} for a, b in edges[i : i + BATCH]]
                s.run(
                    "UNWIND $rows AS r MATCH (a:BNode {id: r.a}), (b:BNode {id: r.b}) "
                    "CREATE (a)-[:BLINK]->(b)",
                    rows=rows,
                ).consume()

    def shortest(self, src: str, dst: str, depth: int):
        query = NEO_PATH.replace("__D__", str(int(depth)))
        with self.driver.session() as s:
            row = s.run(query, src=src, dst=dst).single()
        return row["d"] if row else None

    def cleanup(self) -> None:
        with self.driver.session() as s:
            s.run("MATCH (n:BNode) DETACH DELETE n").consume()
