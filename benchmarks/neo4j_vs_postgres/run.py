"""Benchmark: shortest path between two authors, Neo4j against a PostgreSQL recursive query.

Run from the repo root, with stack B started and a PostgreSQL container on port 5433:
    docker run --name pg-b -e POSTGRES_PASSWORD=pg -p 5433:5432 -d postgres:16
    python -m benchmarks.neo4j_vs_postgres.run                       # the real graph of the project
    python -m benchmarks.neo4j_vs_postgres.run --dataset synthetic   # a bigger graph (20,000 nodes)
For each depth (2 to 5) it picks pairs of authors whose shortest path has exactly that many
links, then times 30 queries on each engine. Output: benchmarks/neo4j_vs_postgres/results/<dataset>/
"""

import argparse
import os
import sys
from pathlib import Path

from benchmarks.neo4j_vs_postgres import graph_data
from benchmarks.neo4j_vs_postgres.measure import summarize, time_calls
from benchmarks.neo4j_vs_postgres.outputs import make_chart, table_markdown, write_results

RESULTS = Path(__file__).with_name("results")


def run_benchmark(engines: dict, pairs: dict, runs: int = 30, warmup: int = 3) -> list[dict]:
    """engines: {name: function(src, dst, depth) -> links}. One row per engine and depth."""
    rows = []
    for depth, depth_pairs in sorted(pairs.items()):
        for name, shortest in engines.items():

            def call(i, shortest=shortest, depth=depth, depth_pairs=depth_pairs):
                src, dst = depth_pairs[i % len(depth_pairs)]
                return shortest(src, dst, depth)

            times, answers = time_calls(call, runs, warmup)
            rows.append(
                {
                    "engine": name,
                    "depth": depth,
                    "pairs": len(depth_pairs),
                    **summarize(times),
                    "wrong_answers": sum(1 for a in answers if a != depth and a != "timeout"),
                    "timeouts": sum(1 for a in answers if a == "timeout"),
                }
            )
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dataset", choices=["real", "synthetic"], default="real")
    ap.add_argument("--nodes", type=int, default=20000, help="synthetic graph: number of nodes")
    ap.add_argument("--edges-per-node", type=int, default=2)
    ap.add_argument("--depths", type=int, nargs="+", default=[2, 3, 4, 5])
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--pairs", type=int, default=10, help="author pairs per depth")
    ap.add_argument(
        "--pg-url", default=os.getenv("PG_URL", "postgresql://postgres:pg@localhost:5433/postgres")
    )
    ap.add_argument(
        "--pg-timeout", type=int, default=20000, help="ms before a PostgreSQL query is cancelled"
    )
    ap.add_argument("--keep", action="store_true", help="keep the BNode copy in Neo4j")
    args = ap.parse_args()

    from neo4j import GraphDatabase

    from backend.app.config import settings
    from benchmarks.neo4j_vs_postgres.engines import NeoEngine, PgEngine

    driver = GraphDatabase.driver(
        settings.neo4j_url, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        driver.verify_connectivity()
    except Exception as exc:
        sys.exit(f"Cannot reach Neo4j ({exc.__class__.__name__}). Is stack B running?")
    try:
        pg = PgEngine(args.pg_url, args.pg_timeout)
    except Exception as exc:
        sys.exit(
            f"Cannot reach PostgreSQL at {args.pg_url} ({exc.__class__.__name__}). "
            "Start the container first."
        )

    if args.dataset == "real":
        nodes, edges = graph_data.read_neo4j_graph(driver)
    else:
        nodes, edges = graph_data.synthetic_graph(args.nodes, args.edges_per_node)
    print(f"Graph '{args.dataset}': {len(nodes)} nodes, {len(edges)} links")
    adj = graph_data.adjacency(edges)
    pairs = graph_data.pairs_by_depth(adj, args.depths, args.pairs)
    missing = [d for d in args.depths if d not in pairs]
    if not pairs:
        sys.exit("No author pair at these depths. Try: --dataset synthetic")
    if missing:
        print(
            f"Warning: no pair at depth {missing} in this graph (it is too small or too connected)."
        )

    print("Loading the graph into PostgreSQL and Neo4j ...")
    pg.load(edges)
    neo = NeoEngine(driver)
    neo.load(nodes, edges)

    print(f"Timing {args.runs} runs per depth and engine ...")
    rows = run_benchmark(
        {"Neo4j": neo.shortest, "PostgreSQL": pg.shortest}, pairs, args.runs, args.warmup
    )
    for r in rows:
        print(
            f"  depth {r['depth']}  {r['engine']:10}  p50={r['p50_ms']:9.2f} ms"
            f"  p95={r['p95_ms']:9.2f} ms  wrong={r['wrong_answers']} timeouts={r['timeouts']}"
        )

    meta = {"dataset": args.dataset, "nodes": len(nodes), "edges": len(edges), "runs": args.runs,
            "warmup": args.warmup, "pg_timeout_ms": args.pg_timeout}  # fmt: skip
    out = write_results(rows, RESULTS / args.dataset, meta)
    chart = make_chart(
        rows,
        out / "chart.png",
        f"Shortest path: Neo4j vs PostgreSQL ({args.dataset} graph, {len(nodes)} nodes)",
    )
    if not args.keep:
        neo.cleanup()
    pg.close()
    driver.close()
    print("\n" + table_markdown(rows))
    print(f"Files written in {out}: results.json, results.csv, results.md, {chart.name}")
    if any(r["wrong_answers"] for r in rows):
        print("WARNING: some answers are wrong. Do not use these numbers before understanding why.")


if __name__ == "__main__":
    main()
