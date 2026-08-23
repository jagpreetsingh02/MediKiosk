"""Declarative base and shared column helpers. Dialect-aware so tests run on SQLite."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def ts_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        default=lambda: datetime.now(UTC), nullable=False,
    )
