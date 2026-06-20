from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Data.database import get_db
from services import google_auth_service

router = APIRouter()


class GoogleAuthUrlResponse(BaseModel):
    auth_url: str
    state: str


class GoogleCallbackBody(BaseModel):
    code: str
    state: str


@router.get("/google/url", response_model=GoogleAuthUrlResponse)
async def google_auth_url():
    """Get the Google OAuth URL for sign-in."""
    try:
        return google_auth_service.get_google_auth_url()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/google/callback")
async def google_callback_get(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """Handle OAuth redirect from Google (GET)."""
    return google_auth_service.signup_or_login(db, code, state)


@router.post("/google/callback")
async def google_callback_post(
    body: GoogleCallbackBody, db: Session = Depends(get_db)
):
    """Exchange an authorization code for a JWT token (POST)."""
    return google_auth_service.signup_or_login(db, body.code, body.state)
