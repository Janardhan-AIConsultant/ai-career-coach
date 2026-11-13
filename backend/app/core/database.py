"""Database engine/session management (SQLAlchemy 2.x).

The engine is a shared, thread-safe client cached per URL. ``get_db`` yields one session per
request and rolls back on error; SQLAlchemy errors are re-raised as ``DatabaseError`` with the
original exception chained (never exposed to clients).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=300)


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("database error", exc_info=exc)
        raise DatabaseError() from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
