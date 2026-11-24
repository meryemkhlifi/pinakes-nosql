from datetime import date, datetime, timezone

from cassandra import DriverException
from cassandra.cluster import NoHostAvailable
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.db import cassandra as events_db

router = APIRouter(prefix="/events", tags=["events"])


class ReadEvent(BaseModel):
    work_id: str = Field(min_length=1, max_length=100)
    user_id: str = Field(min_length=1, max_length=100)


def _call(fn, *args):
    """Call a Cassandra function; turn connection problems into a clear 503."""
    try:
        return fn(*args)
    except (NoHostAvailable, DriverException) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cassandra is not reachable or not initialised. Is stack B running? "
                "Then run: python -m data_pipeline.cassandra.load_events --schema-only"
            ),
        ) from exc


@router.post("/read", status_code=201, summary="Record that a user opened a work")
def record_read(event: ReadEvent):
    _call(events_db.record_read, event.work_id, event.user_id)
    return {"status": "recorded"}


@router.get("/work/{work_id}", summary="Reads of a work on one day")
def reads_of_work(work_id: str, day: date | None = None):
    day = day or datetime.now(timezone.utc).date()
    count = _call(events_db.reads_of_work, work_id, day)
    return {"work_id": work_id, "day": day.isoformat(), "count": count}


@router.get("/user/{user_id}", summary="Reading history of a user")
def reads_of_user(user_id: str, limit: int = Query(20, ge=1, le=200)):
    return _call(events_db.reads_of_user, user_id, limit)
