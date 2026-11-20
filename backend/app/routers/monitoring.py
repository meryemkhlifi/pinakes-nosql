from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
NOT_READY = "Not implemented yet (task B6)"


@router.get("/alerts", summary="Latest anomaly alerts (bot detection)")
def alerts(limit: int = 20):
    raise HTTPException(status_code=501, detail=NOT_READY)
