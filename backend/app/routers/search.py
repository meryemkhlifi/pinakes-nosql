from elasticsearch import ConnectionError, ConnectionTimeout, NotFoundError
from fastapi import APIRouter, HTTPException, Query, Response

from backend.app.db import es as search_db
from backend.app.db import redis as redis_db

router = APIRouter(tags=["search"])
MAX_RESULT_WINDOW = 10_000  # Elasticsearch default limit for from + size


def _call(fn, *args):
    """Call an Elasticsearch function; turn connection problems into a clear 503."""
    try:
        return fn(*args)
    except (ConnectionError, ConnectionTimeout, NotFoundError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Elasticsearch is not reachable or the index is missing. Is stack A running? "
                "Then run: python -m data_pipeline.elastic.load_es"
            ),
        ) from exc


@router.get("/search", summary="Full-text search with typos, filters and facets (cached 60 s)")
def search_works(
    response: Response,
    q: str = Query(..., min_length=1, description="Search text"),
    genre: str | None = None,
    language: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
):
    if year_from is not None and year_to is not None and year_from > year_to:
        raise HTTPException(status_code=422, detail="year_from must be <= year_to")
    if page * size > MAX_RESULT_WINDOW:
        raise HTTPException(status_code=422, detail="page * size must be <= 10000")

    params = dict(q=q.strip().lower(), genre=genre, language=language, year_from=year_from)
    key = redis_db.make_key("search", {**params, "year_to": year_to, "page": page, "size": size})
    cached = redis_db.cache_get(key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached
    result = _call(search_db.search_works, q, genre, language, year_from, year_to, page, size)
    redis_db.cache_set(key, result)
    response.headers["X-Cache"] = "MISS"
    return result


@router.get("/suggest", summary="Autocomplete on titles (cached 60 s)")
def suggest(
    response: Response,
    q: str = Query(..., min_length=1, description="Beginning of a title"),
):
    key = redis_db.make_key("suggest", {"q": q.strip().lower()})
    cached = redis_db.cache_get(key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached
    result = _call(search_db.suggest, q)
    redis_db.cache_set(key, result)
    response.headers["X-Cache"] = "MISS"
    return result
