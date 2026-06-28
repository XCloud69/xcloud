from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Data.database import get_db
from Data.models import User, Task
from services import auth_service, task_service, google_tasks_service
from services.google_auth_service import get_google_credentials

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


def _sync_to_google(user: User, task_dict: dict, db: Session):
    creds = get_google_credentials(user)
    if not creds:
        print(f"[sync] no google creds for user {user.id}")
        return task_dict
    try:
        if task_dict.get("google_task_id"):
            google_tasks_service.update_task(
                user, task_dict["google_task_id"],
                title=task_dict.get("title"),
                notes=task_dict.get("description"),
            )
        else:
            due = None
            if task_dict.get("due_date"):
                from datetime import datetime
                raw = task_dict["due_date"]
                try:
                    dt = datetime.fromisoformat(raw)
                    due = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                except (ValueError, TypeError):
                    due = raw
            result = google_tasks_service.create_task(
                user, task_dict["title"],
                notes=task_dict.get("description") or "",
                due_date_rfc3339=due,
            )
            task_service.set_google_ids(
                db, task_dict["id"],
                google_task_id=result["id"],
                google_task_list_id="@default",
            )
            task_dict["google_task_id"] = result["id"]
            task_dict["google_task_list_id"] = "@default"
            print(f"[sync] created google task {result['id']} for local {task_dict['id']}")
    except Exception as e:
        print(f"[sync] error: {e}")
    return task_dict


def _delete_from_google(user: User, task_dict: dict):
    gid = task_dict.get("google_task_id")
    if not gid:
        return
    creds = get_google_credentials(user)
    if not creds:
        return
    try:
        google_tasks_service.delete_task(user, gid)
    except Exception:
        pass


@router.post("/")
async def create_task(
    body: TaskCreate,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    result = task_service.create_task(
        db, user.id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        due_date=body.due_date,
    )
    return _sync_to_google(user, result, db)


def _pull_tasks_from_google(user: User, db: Session):
    pulled = 0
    existing_ids = {
        t.google_task_id
        for t in db.query(Task).filter(
            Task.user_id == user.id,
            Task.google_task_id.isnot(None),
        ).all()
    }
    for gt in google_tasks_service.list_tasks(user, max_results=100):
        if gt["id"] in existing_ids:
            continue
        due = None
        if gt.get("due"):
            try:
                due = datetime.fromisoformat(gt["due"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        status = "completed" if gt["status"] == "completed" else "pending"
        task_service.create_task(
            db, user.id,
            title=gt.get("title", ""),
            description=gt.get("notes", ""),
            status=status,
            due_date=due,
        )
        pulled += 1
    return pulled


@router.post("/sync")
async def sync_tasks(
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Bidirectional sync: push local unsynced tasks to Google, pull remote tasks to local DB."""
    creds = get_google_credentials(user)
    if not creds:
        raise HTTPException(status_code=400, detail="No Google account linked. Sign in with Google first.")
    unsynced = task_service.list_unsynced_tasks(db, user.id)
    pushed = 0
    for task in unsynced:
        _sync_to_google(user, task, db)
        pushed += 1
    pulled = _pull_tasks_from_google(user, db)
    return {"pushed": pushed, "pulled": pulled}


@router.get("/")
async def list_tasks(
    status: str | None = Query(None),
    priority: str | None = Query(None),
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return task_service.list_tasks(db, user.id, status=status, priority=priority)


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
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
    task = task_service.update_task(
        db, task_id, user.id,
        title=body.title,
        description=body.description,
        status=body.status,
        priority=body.priority,
        due_date=body.due_date,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _sync_to_google(user, task, db)


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    task = task_service.get_task(db, task_id, user.id)
    if task:
        _delete_from_google(user, task)
    if not task_service.delete_task(db, task_id, user.id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "Task deleted"}
