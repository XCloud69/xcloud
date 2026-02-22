"""
Database engine, session, and utilities for Xcloud.
Uses SQLAlchemy with SQLite.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os
import uuid
from datetime import datetime, timezone

# Resolve project root: go up from src/Data/ to project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "xcloud.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def init_db():
    """Create all tables if they don't exist."""
    # Import models so they are registered on Base.metadata
    Base.metadata.create_all(engine)


def get_db():
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
