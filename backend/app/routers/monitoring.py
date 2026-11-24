import httpx
from fastapi import APIRouter, HTTPException, Query

from backend.app.db import es_logs

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/alerts", summary="Latest anomaly alerts (bot detection)")
def alerts(limit: int = Query(20, ge=1, le=200)):
    try:
        return es_logs.latest_alerts(limit)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="Elasticsearch (logs) is not reachable. Is stack B running?",
        ) from exc
