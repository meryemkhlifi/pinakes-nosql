"""MongoDB access and catalog queries (owner: A). Used by routers/catalog.py."""

from functools import lru_cache

from pymongo import MongoClient

from backend.app.config import settings


@lru_cache(maxsize=1)
def get_collection():
    client = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=3000)
    return client["pinakes"]["works"]


def list_genres(collection=None) -> list[dict]:
    collection = collection if collection is not None else get_collection()
    rows = collection.aggregate(
        [{"$group": {"_id": "$genre", "count": {"$sum": 1}}}, {"$sort": {"count": -1, "_id": 1}}]
    )
    return [{"genre": r["_id"], "count": r["count"]} for r in rows]


def authors_of_genre(genre: str, collection=None) -> list[dict]:
    collection = collection if collection is not None else get_collection()
    rows = collection.aggregate(
        [
            {"$match": {"genre": genre}},
            {"$unwind": "$authors"},
            {
                "$group": {
                    "_id": "$authors.id",
                    "name": {"$first": "$authors.name"},
                    "works": {"$push": {"id": "$_id", "title": "$title"}},
                }
            },
            {"$sort": {"name": 1}},
        ]
    )
    return [
        {
            "author_id": r["_id"],
            "name": r["name"],
            "works": sorted(r["works"], key=lambda w: w["title"]),
        }
        for r in rows
    ]


def get_work(work_id: str, collection=None) -> dict | None:
    collection = collection if collection is not None else get_collection()
    return collection.find_one({"_id": work_id})


def titles_of(work_ids: list[str], collection=None) -> dict[str, str]:
    """{work_id: title} for the given ids (used by /popular)."""
    if not work_ids:
        return {}
    collection = collection if collection is not None else get_collection()
    rows = collection.find({"_id": {"$in": list(work_ids)}}, {"title": 1})
    return {r["_id"]: r["title"] for r in rows}
