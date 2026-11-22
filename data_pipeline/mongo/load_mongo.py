"""Load the works into MongoDB and create the indexes (task A3, owner: A).

    python -m data_pipeline.mongo.load_mongo                 # data/raw/works.json if it exists
    python -m data_pipeline.mongo.load_mongo --works data/sample/works_sample.json
Database `pinakes`, collection `works`. Safe to run again (works are replaced by _id).
"""

import argparse
import json
from pathlib import Path

from pymongo import ASCENDING, MongoClient

from backend.app.config import settings

BATCH = 1000


def load(works: list[dict], collection) -> int:
    for i in range(0, len(works), BATCH):
        batch = works[i : i + BATCH]
        # delete then insert: same result as an upsert, and safe to run again
        collection.delete_many({"_id": {"$in": [w["_id"] for w in batch]}})
        collection.insert_many(batch, ordered=False)
    return collection.count_documents({})


def create_indexes(collection) -> None:
    collection.create_index([("genre", ASCENDING)], name="genre")
    collection.create_index([("authors.name", ASCENDING)], name="authors_name")
    collection.create_index([("authors.id", ASCENDING)], name="authors_id")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    default = "data/raw/works.json" if Path("data/raw/works.json").exists() else None
    ap.add_argument("--works", default=default or "data/sample/works_sample.json")
    args = ap.parse_args()

    works = json.loads(Path(args.works).read_text(encoding="utf-8"))
    client = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=5000)
    collection = client["pinakes"]["works"]
    total = load(works, collection)
    create_indexes(collection)
    print(f"{len(works)} works read from {args.works}; the collection now holds {total}.")
    for row in collection.aggregate(
        [{"$group": {"_id": "$genre", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]
    ):
        print(f"  {row['_id']:12} {row['n']}")
    print("Indexes:", sorted(collection.index_information()))


if __name__ == "__main__":
    main()
