"""Database connection helpers (SQLite by default, PostgreSQL-compatible)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)
_engine: Engine | None = None


def configure(url: str) -> Engine:
    """Create the engine for `url` and bind the session factory to it."""
    global _engine
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    SessionLocal.configure(bind=engine)
    _engine = engine
    return engine


def get_engine() -> Engine:
    if _engine is None:
        from .config import get_settings

        configure(get_settings().resolved_database_url)
    assert _engine is not None
    return _engine


def init_db() -> None:
    """Create any missing tables. Safe to run repeatedly."""
    from . import models  # noqa: F401  (registers the tables)

    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    get_engine()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
