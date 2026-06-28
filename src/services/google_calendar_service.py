from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from Data.models import CalendarEvent
from services.google_auth_service import get_google_credentials

# ── Google Calendar API layer ──

def _get_google_service(user):
    creds = get_google_credentials(user)
    if not creds:
        raise ValueError("No Google credentials available")
    return build("calendar", "v3", credentials=creds)


def list_google_events(user, max_results=20, days_ahead=30):
    service = _get_google_service(user)
    now = datetime.now(timezone.utc).isoformat()
    time_max = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat()
    events = service.events().list(
        calendarId="primary", timeMin=now, timeMax=time_max,
        maxResults=max_results, singleEvents=True, orderBy="startTime",
    ).execute()
    result = []
    for e in events.get("items", []):
        result.append({
            "id": e["id"],
            "summary": e.get("summary", ""),
            "description": e.get("description", ""),
            "location": e.get("location", ""),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "end": e["end"].get("dateTime", e["end"].get("date")),
            "htmlLink": e.get("htmlLink", ""),
        })
    return result


def create_google_event(user, summary, start_time, end_time, description="", location=""):
    service = _get_google_service(user)
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    if location:
        body["location"] = location
    event = service.events().insert(calendarId="primary", body=body).execute()
    return {"id": event["id"], "summary": event.get("summary", ""), "htmlLink": event.get("htmlLink", "")}


def update_google_event(user, event_id, summary=None, start_time=None, end_time=None, description=None, location=None):
    service = _get_google_service(user)
    event = service.events().get(calendarId="primary", eventId=event_id).execute()
    if summary is not None:
        event["summary"] = summary
    if description is not None:
        event["description"] = description
    if location is not None:
        event["location"] = location
    if start_time is not None:
        event["start"] = {"dateTime": start_time}
    if end_time is not None:
        event["end"] = {"dateTime": end_time}
    updated = service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
    return {"id": updated["id"], "summary": updated.get("summary", ""), "htmlLink": updated.get("htmlLink", "")}


def delete_google_event(user, event_id):
    service = _get_google_service(user)
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return True


def search_google_events(user, query, max_results=10):
    service = _get_google_service(user)
    now = datetime.now(timezone.utc).isoformat()
    events = service.events().list(
        calendarId="primary", timeMin=now,
        maxResults=max_results, singleEvents=True,
        orderBy="startTime", q=query,
    ).execute()
    result = []
    for e in events.get("items", []):
        result.append({
            "id": e["id"],
            "summary": e.get("summary", ""),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "htmlLink": e.get("htmlLink", ""),
        })
    return result


# ── Local DB calendar event layer ──


def create_event(
    db: Session,
    user_id: str,
    title: str,
    start_time: datetime,
    end_time: datetime,
    description: str | None = None,
    location: str | None = None,
    google_event_id: str | None = None,
) -> dict:
    event = CalendarEvent(
        user_id=user_id, title=title, description=description,
        location=location, start_time=start_time, end_time=end_time,
        google_event_id=google_event_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_to_dict(event)


def list_events(db: Session, user_id: str, days_ahead: int = 30) -> list:
    now = datetime.now()
    time_max = now + timedelta(days=days_ahead)
    events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.start_time >= now,
            CalendarEvent.start_time <= time_max,
        )
        .order_by(CalendarEvent.start_time)
        .all()
    )
    return [_event_to_dict(e) for e in events]


def get_event(db: Session, event_id: str, user_id: str) -> dict | None:
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id, CalendarEvent.user_id == user_id,
    ).first()
    if not event:
        return None
    return _event_to_dict(event)


def update_event(
    db: Session, event_id: str, user_id: str,
    title: str | None = None, description: str | None = None,
    location: str | None = None,
    start_time: datetime | None = None, end_time: datetime | None = None,
    google_event_id: str | None = None,
) -> dict | None:
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id, CalendarEvent.user_id == user_id,
    ).first()
    if not event:
        return None
    if title is not None:
        event.title = title
    if description is not None:
        event.description = description
    if location is not None:
        event.location = location
    if start_time is not None:
        event.start_time = start_time
    if end_time is not None:
        event.end_time = end_time
    if google_event_id is not None:
        event.google_event_id = google_event_id
    event.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)
    return _event_to_dict(event)


def list_unsynced_events(db: Session, user_id: str) -> list:
    events = db.query(CalendarEvent).filter(
        CalendarEvent.user_id == user_id,
        CalendarEvent.google_event_id.is_(None),
    ).all()
    return [_event_to_dict(e) for e in events]


def delete_event(db: Session, event_id: str, user_id: str) -> bool:
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id, CalendarEvent.user_id == user_id,
    ).first()
    if not event:
        return False
    db.delete(event)
    db.commit()
    return True


def _event_to_dict(event: CalendarEvent) -> dict:
    return {
        "id": event.id,
        "user_id": event.user_id,
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "start_time": event.start_time.isoformat() if event.start_time else None,
        "end_time": event.end_time.isoformat() if event.end_time else None,
        "google_event_id": event.google_event_id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
    }
