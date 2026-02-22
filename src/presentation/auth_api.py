"""Auth API - login and signup endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Data.database import get_db
from services import auth_service

router = APIRouter()


class AuthRequest(BaseModel):
    username: str
    password: str


@router.post("/signup")
async def signup(body: AuthRequest, db: Session = Depends(get_db)):
    """Register a new user account."""
    return auth_service.signup(db, body.username, body.password)


@router.post("/login")
async def login(body: AuthRequest, db: Session = Depends(get_db)):
    """Login and receive a JWT token."""
    return auth_service.login(db, body.username, body.password)
