from elasticsearch import ConnectionError, ConnectionTimeout, NotFoundError
from fastapi import APIRouter, HTTPException, Query

from backend.app.db import es as search_db

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


@router.get("/search", summary="Full-text search with typos, filters and facets")
def search_works(
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
    return _call(search_db.search_works, q, genre, language, year_from, year_to, page, size)


@router.get("/suggest", summary="Autocomplete on titles")
def suggest(q: str = Query(..., min_length=1, description="Beginning of a title")):
    return _call(search_db.suggest, q)
