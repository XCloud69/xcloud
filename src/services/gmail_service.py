import base64
from datetime import datetime, timezone
from email.message import EmailMessage
from email import message_from_bytes
from email.utils import parsedate_to_datetime

from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from Data.models import User, EmailAccount, Email
from services.google_auth_service import get_google_credentials


def _get_gmail_service(user: User):
    creds = get_google_credentials(user)
    if not creds:
        raise ValueError("No Google credentials available for this user")
    return build("gmail", "v1", credentials=creds)


def send_email(db: Session, user: User, to: str, subject: str, body: str) -> dict:
    service = _get_gmail_service(user)
    account = (
        db.query(EmailAccount)
        .filter(EmailAccount.user_id == user.id, EmailAccount.provider == "gmail")
        .first()
    )
    if not account:
        raise ValueError("No Gmail account configured")

    message = EmailMessage()
    message.set_content(body)
    message["To"] = to
    message["From"] = user.email or account.email_address
    message["Subject"] = subject

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": encoded})
        .execute()
    )

    email_record = Email(
        user_id=user.id,
        account_id=account.id,
        message_id=sent["id"],
        sender=user.email or account.email_address,
        recipients=to,
        subject=subject,
        body=body,
        folder="sent",
        received_at=datetime.now(timezone.utc),
    )
    db.add(email_record)
    db.commit()
    db.refresh(email_record)

    return _email_to_dict(email_record)


def sync_inbox(
    db: Session, user: User, max_results: int = 50
) -> dict:
    service = _get_gmail_service(user)
    account = (
        db.query(EmailAccount)
        .filter(EmailAccount.user_id == user.id, EmailAccount.provider == "gmail")
        .first()
    )
    if not account:
        raise ValueError("No Gmail account configured")

    seen_mids = {
        mid
        for (mid,) in db.query(Email.message_id)
        .filter(
            Email.account_id == account.id,
            Email.message_id.isnot(None),
            Email.folder == "inbox",
        )
        .all()
    }

    results = (
        service.users()
        .messages()
        .list(userId="me", maxResults=max_results, q="in:inbox")
        .execute()
    )
    messages = results.get("messages", [])
    fetched = 0

    for msg_summary in messages:
        msg_id = msg_summary["id"]
        if msg_id in seen_mids:
            continue

        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="raw")
            .execute()
        )

        raw_bytes = base64.urlsafe_b64decode(msg["raw"])
        parsed = message_from_bytes(raw_bytes)

        sender = parsed.get("From", "")
        recipients = parsed.get("To", "")
        subj = parsed.get("Subject", "")
        received_at = parsed.get("Date")
        body = _get_body(parsed)

        email_record = Email(
            user_id=user.id,
            account_id=account.id,
            message_id=msg_id,
            sender=sender,
            recipients=recipients,
            subject=subj,
            body=body,
            folder="inbox",
            received_at=_parse_date(received_at) if received_at else datetime.now(timezone.utc),
        )
        db.add(email_record)
        fetched += 1

    db.commit()
    return {"synced": fetched, "total_unseen": len(messages)}


def _get_body(parsed) -> str:
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
        return ""
    payload = parsed.get_payload(decode=True)
    return payload.decode("utf-8", errors="replace") if payload else ""


def _parse_date(date_str: str) -> datetime | None:
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def _email_to_dict(email: Email) -> dict:
    return {
        "id": email.id,
        "account_id": email.account_id,
        "message_id": email.message_id,
        "sender": email.sender,
        "recipients": email.recipients,
        "subject": email.subject,
        "body": email.body,
        "is_read": email.is_read,
        "folder": email.folder,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "created_at": email.created_at.isoformat() if email.created_at else None,
    }
