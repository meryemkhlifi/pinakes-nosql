from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from backend.app.db import mongo as catalog_db
from backend.app.db import redis as redis_db

router = APIRouter(tags=["popular"])


@router.get("/popular", summary="Most read works (Redis sorted set)")
def popular(n: int = Query(10, ge=1, le=100)):
    try:
        rows = redis_db.top_works(n)
    except RedisError as exc:
        raise HTTPException(
            status_code=503, detail="Redis is not reachable. Is stack A running?"
        ) from exc
    try:
        titles = catalog_db.titles_of([work_id for work_id, _ in rows])
    except PyMongoError:
        titles = {}  # no title available: show the id instead
    return [{"id": i, "title": titles.get(i, i), "views": views} for i, views in rows]
