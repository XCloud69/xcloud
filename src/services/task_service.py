"""
Task service — CRUD operations for tasks.
"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from Data.models import Task, TaskStatus, TaskPriority


def create_task(
    db: Session,
    user_id: str,
    title: str,
    description: str | None = None,
    priority: str = "medium",
    due_date: datetime | None = None,
) -> dict:
    """Create a new task for a user."""
    task = Task(
        user_id=user_id,
        title=title,
        description=description,
        priority=TaskPriority(priority),
        due_date=due_date,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_to_dict(task)


def list_tasks(
    db: Session,
    user_id: str,
    status: str | None = None,
    priority: str | None = None,
) -> list:
    """List tasks for a user, optionally filtered by status/priority."""
    query = db.query(Task).filter(Task.user_id == user_id)
    if status:
        query = query.filter(Task.status == TaskStatus(status))
    if priority:
        query = query.filter(Task.priority == TaskPriority(priority))
    tasks = query.order_by(Task.created_at.desc()).all()
    return [_task_to_dict(t) for t in tasks]


def get_task(db: Session, task_id: str, user_id: str) -> dict | None:
    """Get a single task."""
    task = db.query(Task).filter(Task.id == task_id,
                                 Task.user_id == user_id).first()
    if not task:
        return None
    return _task_to_dict(task)


def update_task(
    db: Session,
    task_id: str,
    user_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    due_date: datetime | None = None,
) -> dict | None:
    """Update a task. Only provided fields are changed."""
    task = db.query(Task).filter(Task.id == task_id,
                                 Task.user_id == user_id).first()
    if not task:
        return None
    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if status is not None:
        task.status = TaskStatus(status)
    if priority is not None:
        task.priority = TaskPriority(priority)
    if due_date is not None:
        task.due_date = due_date
    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return _task_to_dict(task)


def delete_task(db: Session, task_id: str, user_id: str) -> bool:
    """Delete a task and all its reminders."""
    task = db.query(Task).filter(Task.id == task_id,
                                 Task.user_id == user_id).first()
    if not task:
        return False
    db.delete(task)
    db.commit()
    return True


def _task_to_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "user_id": task.user_id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value if task.status else "pending",
        "priority": task.priority.value if task.priority else "medium",
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }
