from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["popular"])
NOT_READY = "Not implemented yet (task A6)"


@router.get("/popular", summary="Most read works (Redis sorted set)")
def popular(n: int = 10):
    raise HTTPException(status_code=501, detail=NOT_READY)
