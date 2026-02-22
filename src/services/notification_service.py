"""
Notification service — create, list, mark-read, delete notifications.
"""

from sqlalchemy.orm import Session

from Data.models import Notification, NotificationType


def create_notification(
    db: Session,
    user_id: str,
    title: str,
    message: str | None = None,
    notif_type: str = "system",
) -> dict:
    """Create a notification for a user."""
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=NotificationType(notif_type),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return _notif_to_dict(notif)


def list_notifications(
    db: Session, user_id: str, unread_only: bool = False
) -> list:
    """List notifications for a user, newest first."""
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.is_read == False)  # noqa: E712
    notifs = query.order_by(Notification.created_at.desc()).all()
    return [_notif_to_dict(n) for n in notifs]


def unread_count(db: Session, user_id: str) -> int:
    """Return the number of unread notifications."""
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
        .count()
    )


def mark_read(db: Session, notification_id: str, user_id: str) -> dict | None:
    """Mark a single notification as read."""
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id,
                Notification.user_id == user_id)
        .first()
    )
    if not notif:
        return None
    notif.is_read = True
    db.commit()
    db.refresh(notif)
    return _notif_to_dict(notif)


def mark_all_read(db: Session, user_id: str) -> int:
    """Mark all notifications as read. Returns count updated."""
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
        .update({"is_read": True})
    )
    db.commit()
    return count


def delete_notification(db: Session, notification_id: str,
                        user_id: str) -> bool:
    """Delete a notification."""
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id,
                Notification.user_id == user_id)
        .first()
    )
    if not notif:
        return False
    db.delete(notif)
    db.commit()
    return True


def _notif_to_dict(notif: Notification) -> dict:
    return {
        "id": notif.id,
        "user_id": notif.user_id,
        "title": notif.title,
        "message": notif.message,
        "type": notif.type.value if notif.type else "system",
        "is_read": notif.is_read,
        "created_at": notif.created_at.isoformat()
        if notif.created_at else None,
    }
