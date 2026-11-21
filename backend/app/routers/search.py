from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["search"])
NOT_READY = "Not implemented yet (task A5)"


@router.get("/search", summary="Full-text search with typos, filters and facets")
def search_works(
    q: str = Query(..., description="Search text"),
    genre: str | None = None,
    language: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    page: int = 1,
    size: int = 10,
):
    raise HTTPException(status_code=501, detail=NOT_READY)


@router.get("/suggest", summary="Autocomplete on titles")
def suggest(q: str = Query(..., description="Beginning of a title")):
    raise HTTPException(status_code=501, detail=NOT_READY)
