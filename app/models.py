from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    Float,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    """Return the current UTC time."""

    return datetime.now(timezone.utc)


class Job(Base):
    """A job posting imported into JobMatch."""

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

    extraction_method: Mapped[str] = mapped_column(
        String(30),
        default="json_ld",
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

    latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    longitude: Mapped[float | None] = mapped_column(
        Float,
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

    required_skills: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
    )

    preferred_skills: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
    )

    qualifications: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
    )

    soft_skills: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
    )

    languages: Mapped[list[str]] = mapped_column(
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

    application: Mapped[
        "JobApplication | None"
    ] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

class CandidateProfile(Base):
    """The local candidate profile used for job matching."""

    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    full_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    headline: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    max_commute_distance_km: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=30,
        server_default="30",
    )

    years_of_experience: Mapped[float | None] = (
        mapped_column(
            Float,
            nullable=True,
        )
    )

    skills: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    languages: Mapped[list[dict[str, str | None]]] = (
        mapped_column(
            JSON,
            nullable=False,
            default=list,
        )
    )

    preferred_locations: Mapped[list[str]] = (
        mapped_column(
            JSON,
            nullable=False,
            default=list,
        )
    )

    preferred_employment_types: Mapped[list[str]] = (
        mapped_column(
            JSON,
            nullable=False,
            default=list,
        )
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
class JobApplication(Base):
    """Tracks the current state of one job application."""

    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            name="uq_job_applications_job_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey(
            "jobs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="saved",
    )

    applied_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    follow_up_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    last_employer_response_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    next_action: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    job: Mapped["Job"] = relationship(
        back_populates="application",
    )

    events: Mapped[list["ApplicationEvent"]] = (
        relationship(
            back_populates="application",
            cascade="all, delete-orphan",
            order_by="ApplicationEvent.occurred_at",
        )
    )


class ApplicationEvent(Base):
    """An immutable event in an application's history."""

    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    application_id: Mapped[int] = mapped_column(
        ForeignKey(
            "job_applications.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    application: Mapped["JobApplication"] = (
        relationship(
            back_populates="events",
        )
    )
