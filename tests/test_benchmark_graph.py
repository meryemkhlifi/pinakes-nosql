import json
import os

import pytest

from benchmarks.neo4j_vs_postgres import graph_data as g
from benchmarks.neo4j_vs_postgres.engines import NeoEngine, PgEngine
from benchmarks.neo4j_vs_postgres.measure import percentile, summarize, time_calls
from benchmarks.neo4j_vs_postgres.outputs import make_chart, table_markdown, write_results
from benchmarks.neo4j_vs_postgres.run import run_benchmark

PG_TEST_URL = os.getenv("PG_TEST_URL")
needs_pg = pytest.mark.skipif(not PG_TEST_URL, reason="set PG_TEST_URL to test against PostgreSQL")


def test_percentile_matches_the_usual_definition():
    values = list(range(1, 101))
    assert percentile(values, 50) == 50.5
    assert percentile(values, 95) == pytest.approx(95.05)
    assert percentile([7], 95) == 7
    assert percentile([3, 1, 2], 0) == 1 and percentile([3, 1, 2], 100) == 3
    with pytest.raises(ValueError):
        percentile([], 50)


def test_summarize_and_time_calls():
    s = summarize([1.0, 2.0, 3.0, 4.0, 100.0])
    assert s["runs"] == 5 and s["p50_ms"] == 3.0 and s["p95_ms"] > 50 and s["max_ms"] == 100.0
    calls = []
    times, answers = time_calls(lambda i: calls.append(i) or i, runs=30, warmup=3)
    assert calls == list(range(33)) and len(times) == 30 and answers == list(range(3, 33))
    assert all(t >= 0 for t in times)


def test_synthetic_graph_is_connected_and_deterministic():
    nodes, edges = g.synthetic_graph(500, 2, seed=1)
    assert len(nodes) == 500 and len(edges) >= 499
    assert all(a < b for a, b in edges) and len(edges) == len(set(edges))
    assert len(g.bfs_distances(g.adjacency(edges), nodes[0], 10**6)) == 500
    assert (nodes, edges) == g.synthetic_graph(500, 2, seed=1)


def test_pairs_have_exactly_the_requested_distance():
    nodes, edges = g.synthetic_graph(2000, 2)
    adj = g.adjacency(edges)
    pairs = g.pairs_by_depth(adj, [2, 3, 4, 5], per_depth=6)
    assert sorted(pairs) == [2, 3, 4, 5]
    for depth, depth_pairs in pairs.items():
        assert len(depth_pairs) == 6
        for src, dst in depth_pairs:
            assert g.bfs_distances(adj, src, 10)[dst] == depth


def test_missing_depths_are_left_out():
    adj = g.adjacency([("a", "b"), ("b", "c"), ("c", "d")])
    pairs = g.pairs_by_depth(adj, [2, 3, 5], per_depth=2)
    assert sorted(pairs) == [2, 3]  # a path of 4 nodes has no pair at depth 5


def test_run_benchmark_counts_wrong_answers_and_timeouts():
    pairs = {2: [("a", "b"), ("c", "d")], 3: [("e", "f")]}

    def good(src, dst, depth):
        return depth

    def sometimes_wrong(src, dst, depth):
        return "timeout" if src == "c" else depth + 1

    rows = run_benchmark({"good": good, "bad": sometimes_wrong}, pairs, runs=10, warmup=2)
    assert len(rows) == 4
    by = {(r["engine"], r["depth"]): r for r in rows}
    assert by[("good", 2)]["wrong_answers"] == 0 and by[("good", 2)]["runs"] == 10
    assert by[("bad", 2)]["timeouts"] == 5 and by[("bad", 2)]["wrong_answers"] == 5
    assert by[("bad", 3)]["wrong_answers"] == 10


def sample_rows():
    rows = []
    for depth, (n, p) in {2: (1.0, 2.0), 3: (1.5, 15.0)}.items():
        for engine, v in (("Neo4j", n), ("PostgreSQL", p)):
            rows.append({"engine": engine, "depth": depth, "pairs": 10, "runs": 30, "p50_ms": v,
                         "p95_ms": v * 2, "mean_ms": v, "min_ms": v, "max_ms": v * 3,
                         "wrong_answers": 0, "timeouts": 0})  # fmt: skip
    return rows


def test_table_markdown_has_the_ratio():
    table = table_markdown(sample_rows())
    assert "| 2 | 10 | 1.00 | 2.00 | 2.00 | 4.00 | x 2.0 |" in table
    assert "x 10.0" in table


def test_write_results_and_chart(tmp_path):
    meta = {"dataset": "real", "nodes": 126, "edges": 193, "runs": 30, "warmup": 3}
    out = write_results(sample_rows(), tmp_path, meta)
    assert json.loads((out / "results.json").read_text())["meta"]["nodes"] == 126
    assert (out / "results.csv").read_text().splitlines()[0].startswith("engine,depth")
    assert "126 nodes" in (out / "results.md").read_text()
    pytest.importorskip("matplotlib")
    chart = make_chart(sample_rows(), tmp_path / "chart.png", "test")
    assert chart.stat().st_size > 5000


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def single(self):
        return self.row

    def consume(self):
        return None


class FakeSession:
    def __init__(self, log, row):
        self.log, self.row = log, row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self.log.append((" ".join(query.split()), params))
        return FakeResult(self.row)


class FakeDriver:
    def __init__(self, row=None):
        self.log, self.row = [], row

    def session(self):
        return FakeSession(self.log, self.row)


def test_neo4j_engine_query_uses_the_depth_and_the_bench_label():
    driver = FakeDriver(row={"d": 3})
    assert NeoEngine(driver).shortest("a", "b", 3) == 3
    query, params = driver.log[0]
    assert "shortestPath((a)-[:BLINK*..3]-(b))" in query and "BNode" in query
    assert params == {"src": "a", "dst": "b"}
    assert NeoEngine(FakeDriver(row=None)).shortest("a", "b", 2) is None


def test_neo4j_engine_load_never_touches_the_real_graph():
    driver = FakeDriver()
    nodes = [f"n{i}" for i in range(6)]
    NeoEngine(driver).load(nodes, [("n0", "n1"), ("n1", "n2")])
    queries = " ".join(q for q, _ in driver.log)
    assert "Author" not in queries and "BNode" in queries and "BLINK" in queries
    assert driver.log[0][0] == "MATCH (n:BNode) DETACH DELETE n"


@needs_pg
def test_postgres_engine_finds_the_same_distances_as_a_bfs():
    nodes, edges = g.synthetic_graph(1500, 2, seed=3)
    adj = g.adjacency(edges)
    pairs = g.pairs_by_depth(adj, [2, 3, 4], per_depth=5)
    pg = PgEngine(PG_TEST_URL)
    pg.load(edges)
    for depth, depth_pairs in pairs.items():
        for src, dst in depth_pairs:
            assert pg.shortest(src, dst, depth) == depth
    pg.close()


@needs_pg
def test_postgres_engine_handles_cycles_and_unreachable_nodes():
    pg = PgEngine(PG_TEST_URL)
    pg.load([("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"), ("x", "y")])
    assert pg.shortest("a", "d", 5) == 2  # a-c-d, not a-b-c-d
    assert pg.shortest("a", "d", 1) is None  # too far for the depth bound
    assert pg.shortest("a", "y", 5) is None  # another component
    pg.close()
