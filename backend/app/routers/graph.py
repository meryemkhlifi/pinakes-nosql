from fastapi import APIRouter, HTTPException, Query
from neo4j.exceptions import AuthError, ServiceUnavailable

from backend.app.db import neo4j as graph_db

router = APIRouter(prefix="/graph", tags=["graph"])


def _call(fn, *args, **kwargs):
    """Call a Neo4j function; turn connection problems into a clear 503."""
    try:
        return fn(*args, **kwargs)
    except (ServiceUnavailable, AuthError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not reachable. Is stack B running (docker compose ... ps)?",
        ) from exc


@router.get("/path", summary="Shortest path between two authors")
def shortest_path(
    from_: str = Query(..., alias="from", description="Author id, for example a_plato"),
    to: str = Query(..., description="Author id"),
):
    found = _call(graph_db.existing_author_ids, [from_, to])
    missing = [a for a in (from_, to) if a not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Author not found: {', '.join(missing)}")
    return _call(graph_db.shortest_path, from_, to)


@router.get("/neighbors/{author_id}", summary="Authors around one author")
def neighbors(author_id: str, depth: int = Query(2, ge=1, le=4)):
    if _call(graph_db.get_author, author_id) is None:
        raise HTTPException(status_code=404, detail=f"Author not found: {author_id}")
    return _call(graph_db.neighbors, author_id, depth)


@router.get("/influence/top", summary="Most influential authors (PageRank)")
def top_influence(n: int = Query(10, ge=1, le=100)):
    return _call(graph_db.top_influence, n)
