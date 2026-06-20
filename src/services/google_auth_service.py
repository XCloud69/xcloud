import os
import json
import secrets

from fastapi import HTTPException, status
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from Data.models import User, EmailAccount
from services.auth_service import create_access_token

# In-memory store: OAuth state -> PKCE code_verifier
_verifier_store: dict[str, str] = {}

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]

REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/auth/google/callback",
)


def _get_client_config() -> dict:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if client_id and client_secret:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        }

    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    creds_path = os.path.join(project_root, "credentials.json")
    if os.path.exists(creds_path):
        with open(creds_path) as f:
            config = json.load(f)
        if "web" in config or "installed" in config:
            return config
        raise RuntimeError(
            "credentials.json must contain a 'web' or 'installed' key."
        )

    raise RuntimeError(
        "Google OAuth not configured. "
        "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables, "
        "or place a credentials.json file in the project root."
    )


def get_google_auth_url() -> dict:
    flow = Flow.from_client_config(
        _get_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    state = secrets.token_urlsafe(32)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    _verifier_store[state] = flow.code_verifier
    return {"auth_url": auth_url, "state": state}


def exchange_code(code: str, code_verifier: str) -> Credentials:
    flow = Flow.from_client_config(
        _get_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    return flow.credentials


def get_google_user_info(credentials: Credentials) -> dict:
    service = build("oauth2", "v2", credentials=credentials)
    user_info = service.userinfo().get().execute()
    return {
        "google_id": user_info.get("id"),
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "avatar_url": user_info.get("picture"),
    }


def signup_or_login(db: Session, code: str, state: str = "") -> dict:
    code_verifier = _verifier_store.pop(state, None)
    if not code_verifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please sign in again.",
        )
    credentials = exchange_code(code, code_verifier)
    google_info = get_google_user_info(credentials)
    google_id = google_info["google_id"]

    user = db.query(User).filter(User.google_id == google_id).first()

    if user:
        user.google_refresh_token = credentials.refresh_token
        user.avatar_url = google_info.get("avatar_url") or user.avatar_url
        user.email = google_info.get("email") or user.email
        db.commit()
    else:
        username = google_info["email"]
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            username = f"{google_info['email'].split('@')[0]}_{secrets.token_hex(4)}"

        user = User(
            username=username,
            password_hash=None,
            google_id=google_id,
            email=google_info.get("email"),
            avatar_url=google_info.get("avatar_url"),
            google_refresh_token=credentials.refresh_token,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        _ensure_gmail_account(db, user, google_info["email"], credentials.refresh_token)

    token = create_access_token(user.id, user.username)
    return {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "token": token,
    }


def _ensure_gmail_account(
    db: Session, user: User, email: str, refresh_token: str
):
    existing = (
        db.query(EmailAccount)
        .filter(EmailAccount.user_id == user.id, EmailAccount.provider == "gmail")
        .first()
    )
    if existing:
        return

    account = EmailAccount(
        user_id=user.id,
        provider="gmail",
        email_address=email,
    )
    db.add(account)
    db.commit()


def _get_client_info() -> dict:
    config = _get_client_config()
    key = "web" if "web" in config else "installed"
    return config[key]


def get_google_credentials(user: User) -> Credentials | None:
    if not user.google_refresh_token:
        return None
    info = _get_client_info()
    creds = Credentials(
        token=None,
        refresh_token=user.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds
