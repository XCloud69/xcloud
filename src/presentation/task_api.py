"""Task API — CRUD endpoints for tasks."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Data.database import get_db
from Data.models import User
from services import auth_service, task_service

router = APIRouter()


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"
    due_date: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    due_date: datetime | None = None


@router.post("/")
async def create_task(
    body: TaskCreate,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new task."""
    return task_service.create_task(
        db,
        user.id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        due_date=body.due_date,
    )


@router.get("/")
async def list_tasks(
    status: str | None = Query(None),
    priority: str | None = Query(None),
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """List tasks, optionally filtered by status or priority."""
    return task_service.list_tasks(db, user.id, status=status, priority=priority)


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single task."""
    task = task_service.get_task(db, task_id, user.id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}")
async def update_task(
    task_id: str,
    body: TaskUpdate,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Update a task."""
    task = task_service.update_task(
        db,
        task_id,
        user.id,
        title=body.title,
        description=body.description,
        status=body.status,
        priority=body.priority,
        due_date=body.due_date,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a task."""
    if not task_service.delete_task(db, task_id, user.id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "Task deleted"}
