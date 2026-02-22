"""Notification API — endpoints for managing notifications."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from Data.database import get_db
from Data.models import User
from services import auth_service, notification_service

router = APIRouter()


@router.get("/")
async def list_notifications(
    unread_only: bool = False,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """List notifications for the current user."""
    return notification_service.list_notifications(db, user.id, unread_only=unread_only)


@router.get("/unread-count")
async def unread_count(
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Get the number of unread notifications."""
    return {"count": notification_service.unread_count(db, user.id)}


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a notification as read."""
    notif = notification_service.mark_read(db, notification_id, user.id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notif


@router.patch("/read-all")
async def mark_all_read(
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Mark all notifications as read."""
    count = notification_service.mark_all_read(db, user.id)
    return {"status": "All marked as read", "count": count}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a notification."""
    if not notification_service.delete_notification(db, notification_id, user.id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "Notification deleted"}
