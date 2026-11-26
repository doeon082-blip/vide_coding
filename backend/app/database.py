"""SQLite connection and session management (SQLAlchemy 2.x)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _resolve_database_url() -> str:
    """Return DATABASE_URL, anchoring relative SQLite paths to backend/."""
    url = make_url(os.getenv("DATABASE_URL") or "sqlite:///./festivals.db")
    if url.drivername.startswith("sqlite") and url.database not in (None, "", ":memory:"):
        path = Path(url.database)
        if not path.is_absolute():
            url = url.set(database=str((BACKEND_DIR / path).resolve()))
    return url.render_as_string(hide_password=False)


DATABASE_URL = _resolve_database_url()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def init_db() -> None:
    """Create tables if they do not exist."""
    from app import models  # noqa: F401  (register tables on Base.metadata)

    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
