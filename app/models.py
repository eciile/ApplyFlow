from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    """Return the current UTC time."""

    return datetime.now(timezone.utc)


class Job(Base):
    """A job posting imported into ApplyFlow."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    source_url: Mapped[str] = mapped_column(
        Text,
        unique=True,
        index=True,
    )

    final_url: Mapped[str] = mapped_column(
        Text,
    )

    application_url: Mapped[str] = mapped_column(
        Text,
    )

    content_sha256: Mapped[str] = mapped_column(
        String(64),
    )

    title: Mapped[str] = mapped_column(
        String(300),
        index=True,
    )

    company: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
        index=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    employment_types: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
    )

    date_posted: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    valid_through: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )