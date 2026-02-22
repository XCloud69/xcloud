"""Reminder API — endpoints for managing reminders."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Data.database import get_db
from Data.models import User
from services import auth_service, reminder_service

router = APIRouter()


class ReminderCreate(BaseModel):
    task_id: str
    remind_at: datetime


@router.post("/")
async def create_reminder(
    body: ReminderCreate,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Create a reminder for a task."""
    try:
        return reminder_service.create_reminder(
            db, user.id, body.task_id, body.remind_at
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/")
async def list_reminders(
    task_id: str | None = Query(None),
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """List reminders, optionally filtered by task."""
    return reminder_service.list_reminders(db, user.id, task_id=task_id)


@router.delete("/{reminder_id}")
async def delete_reminder(
    reminder_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a reminder."""
    if not reminder_service.delete_reminder(db, reminder_id, user.id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"status": "Reminder deleted"}
