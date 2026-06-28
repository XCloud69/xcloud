import base64
from datetime import datetime, timezone
from email.message import EmailMessage
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from Data.models import User, EmailAccount, Email
from services.google_auth_service import get_google_credentials


def _decode_mime_header(value: str | None) -> str:
    """Decode RFC 2047 encoded-word headers (e.g. =?UTF-8?Q?...?=)."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


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


# Map our app folders to Gmail search queries. Order matters: a message is
# assigned to the first folder it matches (so trash/drafts win over archive).
_FOLDER_QUERIES = [
    ("inbox", "in:inbox"),
    ("sent", "in:sent"),
    ("drafts", "in:drafts"),
    ("trash", "in:trash"),
    # "archive" = everything in All Mail that is not in inbox/sent/trash/drafts/spam.
    ("archive", "-in:inbox -in:sent -in:trash -in:drafts -in:spam"),
]


def sync_inbox(
    db: Session, user: User, max_results: int = 50
) -> dict:
    """Sync the user's Gmail folders into the local store.

    Fetches inbox, sent, drafts, trash and archive, captures read/starred
    state, updates existing rows, inserts new ones, and prunes local rows
    whose Gmail message is no longer present in any synced folder.
    """
    service = _get_gmail_service(user)
    account = (
        db.query(EmailAccount)
        .filter(EmailAccount.user_id == user.id, EmailAccount.provider == "gmail")
        .first()
    )
    if not account:
        raise ValueError("No Gmail account configured")

    # Existing rows keyed by Gmail message id.
    existing = {
        e.message_id: e
        for e in db.query(Email)
        .filter(Email.account_id == account.id, Email.message_id.isnot(None))
        .all()
    }

    # First pass: figure out which folder each message id belongs to.
    folder_of: dict[str, str] = {}
    for folder, query in _FOLDER_QUERIES:
        results = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=query)
            .execute()
        )
        for msg_summary in results.get("messages", []):
            mid = msg_summary["id"]
            folder_of.setdefault(mid, folder)

    fetched = 0
    seen_now: set[str] = set()

    for msg_id, folder in folder_of.items():
        seen_now.add(msg_id)
        row = existing.get(msg_id)

        # Pull the message (metadata for flags, raw for content if new).
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="raw")
            .execute()
        )
        label_ids = set(msg.get("labelIds", []))
        is_starred = "STARRED" in label_ids
        is_read = "UNREAD" not in label_ids

        if row is not None:
            # Update flags/folder on the existing row.
            row.folder = folder
            row.is_starred = is_starred
            row.is_read = is_read
            continue

        raw_bytes = base64.urlsafe_b64decode(msg["raw"])
        parsed = message_from_bytes(raw_bytes)

        email_record = Email(
            user_id=user.id,
            account_id=account.id,
            message_id=msg_id,
            sender=_decode_mime_header(parsed.get("From", "")),
            recipients=_decode_mime_header(parsed.get("To", "")),
            subject=_decode_mime_header(parsed.get("Subject", "")),
            body=_get_body(parsed),
            folder=folder,
            is_read=is_read,
            is_starred=is_starred,
            received_at=_parse_date(parsed.get("Date"))
            if parsed.get("Date")
            else datetime.now(timezone.utc),
        )
        db.add(email_record)
        fetched += 1

    # Prune local rows that no longer exist in any synced Gmail folder
    # (e.g. permanently deleted on Gmail). Keep locally-composed "sent" rows
    # that never got a Gmail message id — those have message_id set, so safe.
    for mid, row in existing.items():
        if mid not in seen_now:
            db.delete(row)

    db.commit()
    return {"synced": fetched, "total_unseen": len(folder_of)}


def archive_message(user: User, message_id: str) -> bool:
    """Archive a Gmail message by removing the INBOX label."""
    if not message_id:
        return False
    try:
        service = _get_gmail_service(user)
        service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["INBOX"]}
        ).execute()
        return True
    except Exception:
        return False


def set_star(user: User, message_id: str, starred: bool) -> bool:
    """Add or remove the Gmail STARRED label (requires gmail.modify scope)."""
    if not message_id:
        return False
    try:
        service = _get_gmail_service(user)
        body = (
            {"addLabelIds": ["STARRED"]}
            if starred
            else {"removeLabelIds": ["STARRED"]}
        )
        service.users().messages().modify(
            userId="me", id=message_id, body=body
        ).execute()
        return True
    except Exception:
        return False


def trash_message(user: User, message_id: str) -> bool:
    """Move a Gmail message to the trash (requires gmail.modify scope)."""
    if not message_id:
        return False
    try:
        service = _get_gmail_service(user)
        service.users().messages().trash(userId="me", id=message_id).execute()
        return True
    except Exception:
        # Already gone on Gmail, or transient error — don't block local delete.
        return False


def _decode_part(part) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, TypeError):
        return payload.decode("utf-8", errors="replace")


def _get_body(parsed) -> str:
    """Extract the richest body available, preferring HTML over plain text."""
    if parsed.is_multipart():
        html_body = ""
        text_body = ""
        for part in parsed.walk():
            if part.get_content_maintype() == "multipart":
                continue
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition.lower():
                continue
            ctype = part.get_content_type()
            if ctype == "text/html" and not html_body:
                html_body = _decode_part(part)
            elif ctype == "text/plain" and not text_body:
                text_body = _decode_part(part)
        return html_body or text_body
    return _decode_part(parsed)


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
        "is_starred": email.is_starred,
        "folder": email.folder,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "created_at": email.created_at.isoformat() if email.created_at else None,
    }


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------


def _account_to_dict(account: EmailAccount) -> dict:
    return {
        "id": account.id,
        "provider": account.provider,
        "email_address": account.email_address,
        "smtp_server": account.smtp_server,
        "smtp_port": account.smtp_port,
        "smtp_username": account.smtp_username,
        "imap_server": account.imap_server,
        "imap_port": account.imap_port,
        "imap_username": account.imap_username,
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }


def get_account(db: Session, user_id: str) -> dict | None:
    account = db.query(EmailAccount).filter(
        EmailAccount.user_id == user_id
    ).first()
    if not account:
        return None
    return _account_to_dict(account)


def save_account(db: Session, user_id: str, data: dict) -> dict:
    existing = db.query(EmailAccount).filter(
        EmailAccount.user_id == user_id
    ).first()

    if existing:
        for field in ("provider", "email_address", "smtp_server", "smtp_port",
                      "imap_server", "imap_port"):
            if field in data:
                setattr(existing, field, data[field])
        if "smtp_username" in data:
            existing.smtp_username = data["smtp_username"]
        if "smtp_password" in data:
            existing.smtp_password = _encrypt(data["smtp_password"])
        if "imap_username" in data:
            existing.imap_username = data["imap_username"]
        if "imap_password" in data:
            existing.imap_password = _encrypt(data["imap_password"])
        db.commit()
        db.refresh(existing)
        return _account_to_dict(existing)

    account = EmailAccount(
        user_id=user_id,
        provider=data.get("provider", "smtp"),
        email_address=data.get("email_address", ""),
        smtp_server=data.get("smtp_server", ""),
        smtp_port=data.get("smtp_port", 587),
        smtp_username=data.get("smtp_username") or data.get("email_address", ""),
        smtp_password=_encrypt(data.get("smtp_password", "")),
        imap_server=data.get("imap_server", ""),
        imap_port=data.get("imap_port", 993),
        imap_username=data.get("imap_username") or data.get("email_address", ""),
        imap_password=_encrypt(data.get("imap_password", "")),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _account_to_dict(account)


def delete_account(db: Session, user_id: str) -> bool:
    account = db.query(EmailAccount).filter(
        EmailAccount.user_id == user_id
    ).first()
    if not account:
        return False
    db.delete(account)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Local email CRUD
# ---------------------------------------------------------------------------


def list_emails(db: Session, user_id: str, folder: str = "inbox",
                page: int = 1, per_page: int = 50) -> list:
    query = db.query(Email).filter(Email.user_id == user_id)
    if folder == "starred":
        query = query.filter(Email.is_starred.is_(True))
    else:
        query = query.filter(Email.folder == folder)
    total = query.count()
    emails = (
        query.order_by(Email.received_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {
        "emails": [_email_to_dict(e) for e in emails],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


def get_email(db: Session, email_id: str, user_id: str) -> dict | None:
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == user_id,
    ).first()
    if not email:
        return None
    return _email_to_dict(email)


def mark_email_read(db: Session, email_id: str, user_id: str) -> dict | None:
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == user_id,
    ).first()
    if not email:
        return None
    email.is_read = True
    db.commit()
    db.refresh(email)
    return _email_to_dict(email)


def set_email_star(db: Session, email_id: str, user_id: str,
                   starred: bool) -> dict | None:
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == user_id,
    ).first()
    if not email:
        return None

    account = db.query(EmailAccount).filter(
        EmailAccount.id == email.account_id
    ).first() if email.account_id else None
    if account and account.provider == "gmail" and email.message_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            set_star(user, email.message_id, starred)

    email.is_starred = starred
    db.commit()
    db.refresh(email)
    return _email_to_dict(email)


def archive_email(db: Session, email_id: str, user_id: str) -> dict | None:
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == user_id,
    ).first()
    if not email:
        return None

    account = db.query(EmailAccount).filter(
        EmailAccount.id == email.account_id
    ).first() if email.account_id else None
    if account and account.provider == "gmail" and email.message_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            archive_message(user, email.message_id)

    email.folder = "archive"
    db.commit()
    db.refresh(email)
    return _email_to_dict(email)


def delete_email(db: Session, email_id: str, user_id: str) -> bool:
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == user_id,
    ).first()
    if not email:
        return False

    account = db.query(EmailAccount).filter(
        EmailAccount.id == email.account_id
    ).first() if email.account_id else None
    if account and account.provider == "gmail" and email.message_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            trash_message(user, email.message_id)

    db.delete(email)
    db.commit()
    return True
