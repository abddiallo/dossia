from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """V1 : création des tables au démarrage. Passer à Alembic dès la première migration."""
    from .models import Base
    Base.metadata.create_all(engine)
    _add_missing_columns()


# Colonnes ajoutées après la première version : create_all ne modifie pas les tables existantes.
_NEW_COLUMNS = [
    ("templates", "source_preview_ids", "VARCHAR(64)[]"),
    ("dossiers", "highlight_preview_ids", "VARCHAR(64)[]"),
]


def _add_missing_columns() -> None:
    from sqlalchemy import text
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for table, col, typ in _NEW_COLUMNS:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}'))
