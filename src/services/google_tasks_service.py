from datetime import datetime, timezone
from googleapiclient.discovery import build
from services.google_auth_service import get_google_credentials


def _get_tasks_service(user):
    creds = get_google_credentials(user)
    if not creds:
        raise ValueError("No Google credentials available")
    return build("tasks", "v1", credentials=creds)


def list_task_lists(user: object) -> list[dict]:
    service = _get_tasks_service(user)
    result = service.tasklists().list().execute()
    return [
        {"id": t["id"], "title": t["title"]}
        for t in result.get("items", [])
    ]


def create_task_list(user: object, title: str) -> dict:
    service = _get_tasks_service(user)
    result = service.tasklists().insert(body={"title": title}).execute()
    return {"id": result["id"], "title": result["title"]}


def delete_task_list(user: object, tasklist_id: str) -> bool:
    service = _get_tasks_service(user)
    service.tasklists().delete(tasklist=tasklist_id).execute()
    return True


def list_tasks(
    user: object,
    tasklist_id: str = "@default",
    max_results: int = 20,
    show_completed: bool = False,
) -> list[dict]:
    service = _get_tasks_service(user)
    result = service.tasks().list(
        tasklist=tasklist_id, maxResults=max_results,
        showCompleted=show_completed,
    ).execute()
    items = []
    for t in result.get("items", []):
        items.append({
            "id": t["id"],
            "title": t.get("title", ""),
            "notes": t.get("notes", ""),
            "status": t.get("status", "needsAction"),
            "due": t.get("due", None),
        })
    return items


def create_task(
    user: object,
    title: str,
    tasklist_id: str = "@default",
    notes: str = "",
    due_date_rfc3339: str | None = None,
) -> dict:
    service = _get_tasks_service(user)
    body = {"title": title}
    if notes:
        body["notes"] = notes
    if due_date_rfc3339:
        body["due"] = due_date_rfc3339
    result = service.tasks().insert(tasklist=tasklist_id, body=body).execute()
    return {"id": result["id"], "title": result["title"]}


def update_task(
    user: object,
    task_id: str,
    tasklist_id: str = "@default",
    title: str | None = None,
    notes: str | None = None,
    due_date_rfc3339: str | None = None,
) -> dict:
    service = _get_tasks_service(user)
    body = {"id": task_id}
    if title is not None:
        body["title"] = title
    if notes is not None:
        body["notes"] = notes if notes else ""
    if due_date_rfc3339 is not None:
        body["due"] = due_date_rfc3339
    result = service.tasks().patch(tasklist=tasklist_id, task=task_id, body=body).execute()
    return {"id": result["id"], "title": result["title"]}


def complete_task(user: object, task_id: str, tasklist_id: str = "@default") -> dict:
    service = _get_tasks_service(user)
    result = service.tasks().update(
        tasklist=tasklist_id, task=task_id,
        body={"status": "completed", "completed": datetime.now(timezone.utc).isoformat()},
    ).execute()
    return {"id": result["id"], "title": result["title"]}


def delete_task(user: object, task_id: str, tasklist_id: str = "@default") -> bool:
    service = _get_tasks_service(user)
    service.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
    return True
