from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/events", tags=["events"])
NOT_READY = "Not implemented yet (task B4)"


class ReadEvent(BaseModel):
    work_id: str
    user_id: str


@router.post("/read", status_code=201, summary="Record that a user opened a work")
def record_read(event: ReadEvent):
    raise HTTPException(status_code=501, detail=NOT_READY)


@router.get("/work/{work_id}", summary="Reads of a work on one day")
def reads_of_work(work_id: str, day: str | None = None):
    raise HTTPException(status_code=501, detail=NOT_READY)


@router.get("/user/{user_id}", summary="Reading history of a user")
def reads_of_user(user_id: str, limit: int = 20):
    raise HTTPException(status_code=501, detail=NOT_READY)
