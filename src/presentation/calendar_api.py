from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Data.database import get_db
from Data.models import User, CalendarEvent
from services import auth_service, google_calendar_service
from services.google_auth_service import get_google_credentials

router = APIRouter()


class EventCreate(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime
    description: str | None = None
    location: str | None = None


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    location: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


def _ensure_tz(s: str | None) -> str | None:
    if s and "T" in s and not s.endswith("Z") and "+" not in s and "-" not in s[10:]:
        return s + "Z"
    return s


def _sync_to_google(user: User, event_dict: dict, db: Session):
    creds = get_google_credentials(user)
    if not creds:
        print(f"[sync-cal] no google creds for user {user.id}")
        return event_dict
    try:
        start = _ensure_tz(event_dict.get("start_time"))
        end = _ensure_tz(event_dict.get("end_time"))
        if event_dict.get("google_event_id"):
            google_calendar_service.update_google_event(
                user, event_dict["google_event_id"],
                summary=event_dict.get("title"),
                description=event_dict.get("description"),
                location=event_dict.get("location"),
                start_time=start,
                end_time=end,
            )
            print(f"[sync-cal] updated google event {event_dict['google_event_id']}")
        else:
            result = google_calendar_service.create_google_event(
                user,
                summary=event_dict["title"],
                start_time=start,
                end_time=end,
                description=event_dict.get("description") or "",
                location=event_dict.get("location") or "",
            )
            google_calendar_service.update_event(
                db, event_dict["id"], user.id,
                google_event_id=result["id"],
            )
            event_dict["google_event_id"] = result["id"]
            print(f"[sync-cal] created google event {result['id']} for local {event_dict['id']}")
    except Exception as e:
        print(f"[sync-cal] error: {e}")
    return event_dict


def _delete_from_google(user: User, event_dict: dict):
    gid = event_dict.get("google_event_id")
    if not gid:
        return
    creds = get_google_credentials(user)
    if not creds:
        return
    try:
        google_calendar_service.delete_google_event(user, gid)
    except Exception:
        pass


@router.post("/")
async def create_event(
    body: EventCreate,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    result = google_calendar_service.create_event(
        db, user.id,
        title=body.title,
        start_time=body.start_time,
        end_time=body.end_time,
        description=body.description,
        location=body.location,
    )
    return _sync_to_google(user, result, db)


def _pull_from_google(user: User, db: Session):
    pulled = 0
    existing_ids = {
        e.google_event_id
        for e in db.query(CalendarEvent).filter(
            CalendarEvent.user_id == user.id,
            CalendarEvent.google_event_id.isnot(None),
        ).all()
    }
    for ge in google_calendar_service.list_google_events(user, max_results=100, days_ahead=365):
        if ge["id"] in existing_ids:
            continue
        start = datetime.fromisoformat(ge["start"].replace("Z", "+00:00")) if ge.get("start") else None
        end = datetime.fromisoformat(ge["end"].replace("Z", "+00:00")) if ge.get("end") else None
        google_calendar_service.create_event(
            db, user.id,
            title=ge.get("summary", ""),
            description=ge.get("description", ""),
            location=ge.get("location", ""),
            start_time=start or datetime.now(),
            end_time=end or datetime.now(),
            google_event_id=ge["id"],
        )
        pulled += 1
    return pulled


@router.post("/sync")
async def sync_events(
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Bidirectional sync: push local unsynced events to Google, pull remote events to local DB."""
    creds = get_google_credentials(user)
    if not creds:
        raise HTTPException(status_code=400, detail="No Google account linked. Sign in with Google first.")
    unsynced = google_calendar_service.list_unsynced_events(db, user.id)
    pushed = 0
    for event in unsynced:
        _sync_to_google(user, event, db)
        pushed += 1
    pulled = _pull_from_google(user, db)
    return {"pushed": pushed, "pulled": pulled}


@router.get("/")
async def list_events(
    days_ahead: int = Query(30),
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return google_calendar_service.list_events(db, user.id, days_ahead=days_ahead)


@router.get("/{event_id}")
async def get_event(
    event_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    event = google_calendar_service.get_event(db, event_id, user.id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/{event_id}")
async def update_event(
    event_id: str,
    body: EventUpdate,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    event = google_calendar_service.update_event(
        db, event_id, user.id,
        title=body.title,
        description=body.description,
        location=body.location,
        start_time=body.start_time,
        end_time=body.end_time,
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _sync_to_google(user, event, db)


@router.delete("/{event_id}")
async def delete_event(
    event_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    event = google_calendar_service.get_event(db, event_id, user.id)
    if event:
        _delete_from_google(user, event)
    if not google_calendar_service.delete_event(db, event_id, user.id):
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "Event deleted"}
