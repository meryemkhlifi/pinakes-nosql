from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/graph", tags=["graph"])
NOT_READY = "Not implemented yet (task B3)"


@router.get("/path", summary="Shortest path between two authors")
def shortest_path(
    from_: str = Query(..., alias="from", description="Author id, for example a_plato"),
    to: str = Query(..., description="Author id"),
):
    raise HTTPException(status_code=501, detail=NOT_READY)


@router.get("/neighbors/{author_id}", summary="Authors around one author")
def neighbors(author_id: str, depth: int = 2):
    raise HTTPException(status_code=501, detail=NOT_READY)


@router.get("/influence/top", summary="Most influential authors (PageRank)")
def top_influence(n: int = 10):
    raise HTTPException(status_code=501, detail=NOT_READY)
