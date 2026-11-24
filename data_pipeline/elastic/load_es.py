"""Create the index `works` and bulk-load it from MongoDB (task A5, owner: A).

Run from the repo root, with stack A started and MongoDB loaded (Day 2):
    python -m data_pipeline.elastic.load_es              # create if missing, then load
    python -m data_pipeline.elastic.load_es --recreate   # delete the index first
Safe to run again: documents are replaced by id.
"""

import argparse

from elasticsearch import Elasticsearch, helpers
from pymongo import MongoClient

from backend.app.config import settings
from data_pipeline.elastic.index_config import INDEX, MAPPINGS, SETTINGS, work_to_doc


def create_index(client, recreate: bool = False) -> bool:
    """Return True when the index was created."""
    exists = client.indices.exists(index=INDEX)
    if exists and recreate:
        client.indices.delete(index=INDEX)
        exists = False
    if not exists:
        client.indices.create(index=INDEX, settings=SETTINGS, mappings=MAPPINGS)
    return not exists


def actions(collection):
    for work in collection.find({}):
        yield {
            "_op_type": "index",
            "_index": INDEX,
            "_id": work["_id"],
            "_source": work_to_doc(work),
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--recreate", action="store_true")
    args = ap.parse_args()

    es = Elasticsearch(settings.es_catalog_url, request_timeout=30)
    mongo = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=5000)["pinakes"]["works"]
    total = mongo.count_documents({})
    if total == 0:
        raise SystemExit("MongoDB has no works. Run: python -m data_pipeline.mongo.load_mongo")

    created = create_index(es, args.recreate)
    print("Index created." if created else "Index already exists, documents will be replaced.")
    ok, errors = helpers.bulk(
        es, actions(mongo), chunk_size=1000, stats_only=True, raise_on_error=False
    )
    es.indices.refresh(index=INDEX)
    held = es.count(index=INDEX)["count"]
    print(f"{ok} documents indexed, {errors} errors. The index now holds {held}.")


if __name__ == "__main__":
    main()
