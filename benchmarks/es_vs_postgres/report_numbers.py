"""Print the numbers of member A for the report (sections 1 to 3), as Markdown (owner: A).

Start stack A (MongoDB, Elasticsearch, Redis), then from the repo root:
    python -m benchmarks.es_vs_postgres.report_numbers
Copy what it prints into docs/a_rapport_sections_1-3.md, in place of the [A REMPLIR] marks.
"""

from backend.app.config import settings


def mongo_numbers() -> list[str]:
    from pymongo import MongoClient

    coll = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=4000)["pinakes"]["works"]
    total = coll.count_documents({})
    genres = coll.aggregate([{"$group": {"_id": "$genre", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}])
    authors = len(coll.distinct("authors.id"))
    return [
        "## MongoDB",
        f"- Works: {total}, distinct authors: {authors}",
        "- Works per genre: " + ", ".join(f"{g['_id']} {g['n']}" for g in genres),
        "- Indexes: " + ", ".join(sorted(coll.index_information())),
    ]


def elastic_numbers() -> list[str]:
    from elasticsearch import Elasticsearch

    es = Elasticsearch(settings.es_catalog_url, request_timeout=10)
    return ["## Elasticsearch", f"- Documents in index `works`: {es.count(index='works')['count']}"]


def redis_numbers() -> list[str]:
    from backend.app.db import redis as redis_db

    stats = redis_db.cache_stats()
    lines = [
        "## Redis",
        f"- Cache: {stats['hits']} hits, {stats['misses']} misses, hit ratio {stats['hit_ratio']}",
    ]
    for work_id, views in redis_db.top_works(3):
        lines.append(f"- Most read: {work_id} ({views} views)")
    return lines


def main():
    for name, fn in (
        ("MongoDB", mongo_numbers),
        ("Elasticsearch", elastic_numbers),
        ("Redis", redis_numbers),
    ):
        try:
            print("\n".join(fn()) + "\n")
        except Exception as exc:  # one service off must not hide the others
            print(f"## {name}\n- not available ({exc.__class__.__name__}: {exc})\n")


if __name__ == "__main__":
    main()
