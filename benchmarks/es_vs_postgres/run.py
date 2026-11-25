"""Benchmark: full-text search, Elasticsearch against PostgreSQL (owner: A).

Run from the repo root, with stack A started (MongoDB, Elasticsearch) and a PostgreSQL container:
    docker run --name pg -e POSTGRES_PASSWORD=pg -p 5432:5432 -d postgres:16
    python -m benchmarks.es_vs_postgres.run
The catalog of MongoDB is copied into both engines. With --target-docs (default 50,000) it is
multiplied with generated works, because 5,000 documents are too few to see a difference.
Output: benchmarks/es_vs_postgres/results/
"""

import argparse
import os
import sys
from pathlib import Path

from benchmarks.es_vs_postgres.measure import summarize, time_calls
from benchmarks.es_vs_postgres.outputs import make_chart, table_markdown, write_results

RESULTS = Path(__file__).with_name("results")
# (text, kind): a common word, two words, and a typo
DEFAULT_QUERIES = [("republic", "exact"), ("history of rome", "exact"), ("republc", "fuzzy")]


def parse_query(text: str) -> tuple[str, str]:
    """'republc:fuzzy' -> ('republc', 'fuzzy'); no suffix means exact."""
    if text.endswith(":fuzzy") or text.endswith(":exact"):
        word, kind = text.rsplit(":", 1)
        return word, kind
    return text, "exact"


def run_queries(engines: dict, queries: list, runs: int = 30, warmup: int = 3) -> list[dict]:
    """engines: {name: object with search(text, kind) and count(text, kind)}."""
    rows = []
    for text, kind in queries:
        for name, engine in engines.items():
            times, answers = time_calls(
                lambda i, e=engine, t=text, k=kind: e.search(t, k), runs, warmup
            )
            first = answers[0] if answers else []
            rows.append(
                {
                    "engine": name,
                    "query": text,
                    "kind": kind,
                    "matches": engine.count(text, kind),
                    **summarize(times),
                    "top_titles": [title for _, title in first[:3]],
                }
            )
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--target-docs", type=int, default=50000, help="0 = only the real works")
    ap.add_argument(
        "--queries", nargs="+", help="for example: republic 'history of rome' republc:fuzzy"
    )
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument(
        "--pg-url", default=os.getenv("PG_URL", "postgresql://postgres:pg@localhost:5432/postgres")
    )
    ap.add_argument("--pg-timeout", type=int, default=20000)
    ap.add_argument(
        "--keep", action="store_true", help="keep the bench_works index in Elasticsearch"
    )
    args = ap.parse_args()
    queries = [parse_query(q) for q in args.queries] if args.queries else DEFAULT_QUERIES

    from elasticsearch import Elasticsearch
    from pymongo import MongoClient

    from backend.app.config import settings
    from benchmarks.es_vs_postgres.corpus import real_corpus, scale_corpus
    from benchmarks.es_vs_postgres.engines import EsSearch, PgSearch

    mongo = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=5000)["pinakes"]["works"]
    try:
        real = real_corpus(mongo)
    except Exception as exc:
        sys.exit(f"Cannot read MongoDB ({exc.__class__.__name__}). Is stack A running and loaded?")
    if not real:
        sys.exit("MongoDB has no works. Run: python -m data_pipeline.mongo.load_mongo")
    docs = scale_corpus(real, args.target_docs)
    print(f"Corpus: {len(docs)} documents ({len(real)} real works)")

    es_client = Elasticsearch(settings.es_catalog_url, request_timeout=60)
    try:
        es_client.info()
    except Exception as exc:
        sys.exit(f"Cannot reach Elasticsearch ({exc.__class__.__name__}). Is stack A running?")
    try:
        pg = PgSearch(args.pg_url, args.pg_timeout)
    except Exception as exc:
        sys.exit(
            f"Cannot reach PostgreSQL at {args.pg_url} ({exc.__class__.__name__}). "
            "Start the container first."
        )

    print("Loading PostgreSQL (table + GIN indexes) ...")
    pg.load(docs)
    print("Loading Elasticsearch (index bench_works) ...")
    es = EsSearch(es_client)
    es.load(docs)

    print(f"Timing {args.runs} runs per query and engine ...")
    rows = run_queries({"Elasticsearch": es, "PostgreSQL": pg}, queries, args.runs, args.warmup)
    for r in rows:
        print(
            f"  {r['query']:18} {r['engine']:14} p50={r['p50_ms']:8.2f} ms"
            f"  p95={r['p95_ms']:8.2f} ms  matches={r['matches']}"
        )
    took = sorted(es.took_ms)
    meta = {"docs": len(docs), "real_docs": len(real), "runs": args.runs, "warmup": args.warmup,
            "es_took_median_ms": took[len(took) // 2] if took else None}  # fmt: skip
    out = write_results(rows, RESULTS, meta)
    title = f"Full-text search: Elasticsearch vs PostgreSQL ({len(docs)} documents)"
    chart = make_chart(rows, out / "chart.png", title)
    if not args.keep:
        es.cleanup()
    pg.close()
    print("\n" + table_markdown(rows))
    print(f"Files written in {out}: results.json, results.csv, results.md, {chart.name}")


if __name__ == "__main__":
    main()
