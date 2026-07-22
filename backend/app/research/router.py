from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.research import service
from app.research.schemas import ResearchRequestIn, ResearchTaskOut

router = APIRouter()


@router.post("/bikes/{bike_id}/populate", response_model=list[ResearchTaskOut])
def populate_bike(
    bike_id: int, db: Annotated[Session, Depends(get_db)]
) -> list[ResearchTaskOut]:
    return [
        ResearchTaskOut.model_validate(task) for task in service.populate_bike(db, bike_id)
    ]


@router.post("/bikes/{bike_id}/tasks", response_model=ResearchTaskOut)
def request_research(
    bike_id: int, payload: ResearchRequestIn, db: Annotated[Session, Depends(get_db)]
) -> ResearchTaskOut:
    task = service.request_research(db, bike_id, payload.kind, payload.fact_key)
    return ResearchTaskOut.model_validate(task)


@router.get("/bikes/{bike_id}/tasks", response_model=list[ResearchTaskOut])
def get_bike_tasks(
    bike_id: int, db: Annotated[Session, Depends(get_db)]
) -> list[ResearchTaskOut]:
    return [
        ResearchTaskOut.model_validate(task)
        for task in service.get_tasks_for_bike(db, bike_id)
    ]


@router.get("/tasks/{task_id}", response_model=ResearchTaskOut)
def get_task(task_id: int, db: Annotated[Session, Depends(get_db)]) -> ResearchTaskOut:
    return ResearchTaskOut.model_validate(service.get_task(db, task_id))
