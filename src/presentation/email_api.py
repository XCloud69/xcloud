"""Email API — send, receive, and manage emails via Gmail API."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Data.database import get_db, SessionLocal
from Data.models import User
from services import auth_service, gmail_service

router = APIRouter()


class AccountConfig(BaseModel):
    email_address: str
    smtp_server: str
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str
    imap_server: str
    imap_port: int = 993
    imap_username: str | None = None
    imap_password: str


class SendEmailBody(BaseModel):
    to: str
    subject: str
    body: str


# ---------------------------------------------------------------------------
# Account management
# ---------------------------------------------------------------------------


@router.get("/account")
async def get_account(
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Get the configured email account."""
    account = gmail_service.get_account(db, user.id)
    if not account:
        raise HTTPException(status_code=404, detail="No email account configured")
    return account


@router.post("/account")
async def configure_account(
    body: AccountConfig,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update email account configuration."""
    return gmail_service.save_account(db, user.id, body.model_dump())


@router.delete("/account")
async def remove_account(
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the configured email account."""
    if not gmail_service.delete_account(db, user.id):
        raise HTTPException(status_code=404, detail="No email account configured")
    return {"status": "Account removed"}


# ---------------------------------------------------------------------------
# Send & sync (run in thread pool with dedicated DB sessions)
# ---------------------------------------------------------------------------


def _send_email_sync(user: User, to: str, subject: str, body: str) -> dict:
    db = SessionLocal()
    try:
        return gmail_service.send_email(db, user, to, subject, body)
    finally:
        db.close()


def _sync_inbox_sync(user: User) -> dict:
    db = SessionLocal()
    try:
        return gmail_service.sync_inbox(db, user)
    finally:
        db.close()


@router.post("/send")
async def send_email(
    body: SendEmailBody,
    user: User = Depends(auth_service.get_current_user),
):
    """Send an email via Gmail API."""
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, _send_email_sync, user, body.to, body.subject, body.body
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {e}")


@router.post("/sync")
async def sync_emails(
    user: User = Depends(auth_service.get_current_user),
):
    """Sync emails from Gmail."""
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, _sync_inbox_sync, user
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail sync failed: {e}")


# ---------------------------------------------------------------------------
# Email CRUD
# ---------------------------------------------------------------------------


@router.get("/")
async def list_emails(
    folder: str = Query("inbox"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """List emails in a folder, paginated."""
    return gmail_service.list_emails(db, user.id, folder=folder, page=page, per_page=per_page)


@router.get("/{email_id}")
async def get_email(
    email_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single email by ID."""
    email = gmail_service.get_email(db, email_id, user.id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@router.patch("/{email_id}/read")
async def mark_email_read(
    email_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Mark an email as read."""
    email = gmail_service.mark_email_read(db, email_id, user.id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


class StarBody(BaseModel):
    starred: bool = True


@router.patch("/{email_id}/star")
async def set_email_star(
    email_id: str,
    body: StarBody,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Star or unstar an email (also updates Gmail)."""
    email = gmail_service.set_email_star(db, email_id, user.id, body.starred)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@router.patch("/{email_id}/archive")
async def archive_email(
    email_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Archive an email (remove from inbox; also updates Gmail)."""
    email = gmail_service.archive_email(db, email_id, user.id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@router.delete("/{email_id}")
async def delete_email(
    email_id: str,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an email."""
    if not gmail_service.delete_email(db, email_id, user.id):
        raise HTTPException(status_code=404, detail="Email not found")
    return {"status": "Email deleted"}
