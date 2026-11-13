"""Declarative base, shared column helpers and CHECK-constraint builders."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

# Portable JSON (JSONB on PostgreSQL, JSON elsewhere).
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def in_check(column: str, values: Iterable[Any], name: str, nullable: bool = False) -> CheckConstraint:
    """CHECK (column IN (...)) built from the constants module so DB and code agree."""
    rendered = ", ".join(f"'{v}'" if isinstance(v, str) else str(int(v)) for v in values)
    expr = f"{column} IN ({rendered})"
    if nullable:
        expr = f"{column} IS NULL OR {expr}"
    return CheckConstraint(expr, name=name)


def fk(
    target: str,
    *,
    nullable: bool = False,
    ondelete: str = "CASCADE",
    unique: bool = False,
) -> Any:
    return mapped_column(
        Uuid, ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True, unique=unique
    )
