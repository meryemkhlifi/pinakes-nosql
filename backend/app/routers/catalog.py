from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/catalog", tags=["catalog"])
NOT_READY = "Not implemented yet (task A3)"


@router.get("/genres", summary="List genres with the number of works")
def list_genres():
    raise HTTPException(status_code=501, detail=NOT_READY)


@router.get("/genres/{genre}/authors", summary="Authors of a genre with their works")
def authors_of_genre(genre: str):
    raise HTTPException(status_code=501, detail=NOT_READY)


@router.get("/works/{work_id}", summary="One work (also counts a view in Redis)")
def get_work(work_id: str):
    raise HTTPException(status_code=501, detail=NOT_READY)
