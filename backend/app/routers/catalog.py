from fastapi import APIRouter, HTTPException
from pymongo.errors import PyMongoError

from backend.app.db import mongo as catalog_db
from backend.app.db import redis as redis_db

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _call(fn, *args):
    """Call a MongoDB function; turn connection problems into a clear 503."""
    try:
        return fn(*args)
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail="MongoDB is not reachable. Is stack A running (docker compose ... ps)?",
        ) from exc


@router.get("/genres", summary="List genres with the number of works")
def list_genres():
    return _call(catalog_db.list_genres)


@router.get("/genres/{genre}/authors", summary="Authors of a genre with their works")
def authors_of_genre(genre: str):
    authors = _call(catalog_db.authors_of_genre, genre)
    if not authors:
        raise HTTPException(status_code=404, detail=f"Genre not found: {genre}")
    return authors


@router.get("/works/{work_id}", summary="One work (counts one view in Redis)")
def get_work(work_id: str):
    work = _call(catalog_db.get_work, work_id)
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work not found: {work_id}")
    redis_db.record_view(work_id)
    return work
