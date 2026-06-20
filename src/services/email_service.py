"""
Email service — send via SMTP, receive via IMAP, account management.
"""

import imaplib
import smtplib
import email as email_lib
import hashlib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet

from Data.models import User, EmailAccount, Email

_IMAP_TIMEOUT = 30
_SMTP_TIMEOUT = 30

# Derive a Fernet key from the app secret (same key used by auth_service)
_KEY_SEED = "xcloud-secret-key-change-in-production"
_FERNET_KEY = base64.urlsafe_b64encode(
    hashlib.sha256(_KEY_SEED.encode()).digest()
)
_cipher = Fernet(_FERNET_KEY)


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _encrypt(plain: str) -> str:
    if not plain:
        return ""
    return _cipher.encrypt(plain.encode()).decode()


def _decrypt(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    return _cipher.decrypt(cipher_text.encode()).decode()


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------

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
# Send email via SMTP
# ---------------------------------------------------------------------------

def send_email(db: Session, user_id: str, to: str, subject: str,
               body: str) -> dict:
    account = db.query(EmailAccount).filter(
        EmailAccount.user_id == user_id
    ).first()
    if not account:
        raise ValueError("No email account configured")

    if account.provider == "gmail":
        from services.gmail_service import send_email as gmail_send
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        return gmail_send(db, user, to, subject, body)

    msg = MIMEMultipart()
    msg["From"] = account.email_address
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    smtp_password = _decrypt(account.smtp_password)
    smtp_username = account.smtp_username or account.email_address

    with smtplib.SMTP(
        account.smtp_server, account.smtp_port, timeout=_SMTP_TIMEOUT
    ) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(account.email_address, [to], msg.as_string())

    email_record = Email(
        user_id=user_id,
        account_id=account.id,
        sender=account.email_address,
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


# ---------------------------------------------------------------------------
# Receive / sync emails via IMAP
# ---------------------------------------------------------------------------

def sync_inbox(db: Session, user_id: str) -> dict:
    """Fetch unseen emails from IMAP and store them locally."""
    account = db.query(EmailAccount).filter(
        EmailAccount.user_id == user_id
    ).first()
    if not account:
        raise ValueError("No email account configured")

    if account.provider == "gmail":
        from services.gmail_service import sync_inbox as gmail_sync
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        return gmail_sync(db, user)

    imap_password = _decrypt(account.imap_password)
    imap_username = account.imap_username or account.email_address

    mail = imaplib.IMAP4_SSL(
        account.imap_server,
        account.imap_port,
        timeout=_IMAP_TIMEOUT,
    )
    try:
        mail.login(imap_username, imap_password)
        mail.select("inbox")

        _, data = mail.search(None, "UNSEEN")
        new_ids = data[0].split() if data[0] else []
        fetched, total = 0, len(new_ids)

        seen_mids = {
            mid for (mid,) in db.query(Email.message_id).filter(
                Email.account_id == account.id,
                Email.message_id.isnot(None),
            ).all()
        }

        for uid in new_ids:
            _, msg_data = mail.fetch(uid, "(RFC822)")
            raw_email = msg_data[0][1]
            parsed = email_lib.message_from_bytes(raw_email)

            msg_id = parsed.get("Message-ID", uid.decode())
            if msg_id in seen_mids:
                continue

            sender = parsed.get("From", "")
            recipients = parsed.get("To", "")
            subject = parsed.get("Subject", "")
            body = _get_email_body(parsed)
            received_at = parsed.get("Date")

            email_record = Email(
                user_id=user_id,
                account_id=account.id,
                message_id=msg_id,
                sender=sender,
                recipients=recipients,
                subject=subject,
                body=body,
                folder="inbox",
                received_at=_parse_email_date(received_at) if received_at else datetime.now(timezone.utc),
            )
            db.add(email_record)
            fetched += 1

        db.commit()
        return {"synced": fetched, "total_unseen": total}
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def _get_email_body(parsed: email_lib.message.Message) -> str:
    """Extract plain text body from an email message."""
    if parsed.is_multipart():
        for part in parsed.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
        return ""
    payload = parsed.get_payload(decode=True)
    return payload.decode("utf-8", errors="replace") if payload else ""


def _parse_email_date(date_str: str) -> datetime | None:
    """Parse an email date string into a datetime."""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Local email CRUD
# ---------------------------------------------------------------------------

def list_emails(db: Session, user_id: str, folder: str = "inbox",
                page: int = 1, per_page: int = 50) -> list:
    query = db.query(Email).filter(
        Email.user_id == user_id,
        Email.folder == folder,
    )
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


def delete_email(db: Session, email_id: str, user_id: str) -> bool:
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == user_id,
    ).first()
    if not email:
        return False
    db.delete(email)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Serializers
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
