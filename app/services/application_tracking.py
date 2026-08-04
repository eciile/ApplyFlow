"""Application tracking and provisional ghosting calculations."""

from dataclasses import dataclass
from datetime import date, datetime

from app.schemas import ApplicationStatus


GHOSTING_THRESHOLD_DAYS = 21

ACTIVE_RESPONSE_STATUSES = {
    ApplicationStatus.APPLIED,
    ApplicationStatus.PREPARING,
}


@dataclass(frozen=True)
class GhostingAssessment:
    """Computed response-waiting information."""

    days_without_response: int | None
    possibly_ghosted: bool
    ghosting_threshold_days: int


def assess_possible_ghosting(
    *,
    status: ApplicationStatus | str,
    applied_at: date | None,
    last_employer_response_at: datetime | None,
    current_date: date | None = None,
    threshold_days: int = GHOSTING_THRESHOLD_DAYS,
) -> GhostingAssessment:
    """
    Assess whether an application may have been ghosted.

    This is a provisional rule. Historical response statistics
    will replace or improve it in a later feature.
    """

    today = current_date or date.today()

    try:
        normalized_status = ApplicationStatus(status)
    except ValueError:
        normalized_status = status

    if applied_at is None:
        return GhostingAssessment(
            days_without_response=None,
            possibly_ghosted=False,
            ghosting_threshold_days=threshold_days,
        )

    if last_employer_response_at is not None:
        return GhostingAssessment(
            days_without_response=None,
            possibly_ghosted=False,
            ghosting_threshold_days=threshold_days,
        )

    elapsed_days = max(
        (today - applied_at).days,
        0,
    )

    possibly_ghosted = (
        normalized_status in ACTIVE_RESPONSE_STATUSES
        and elapsed_days >= threshold_days
    )

    return GhostingAssessment(
        days_without_response=elapsed_days,
        possibly_ghosted=possibly_ghosted,
        ghosting_threshold_days=threshold_days,
    )