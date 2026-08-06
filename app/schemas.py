from datetime import date, datetime
from enum import StrEnum
from ipaddress import ip_address

from pydantic import (  # type: ignore[reportMissingImports]
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from app.text_utils import repair_utf8_mojibake

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
}


class JobUrlRequest(BaseModel):
    """Request body containing a job-posting URL."""

    url: HttpUrl = Field(
        description="Public HTTP or HTTPS URL of a job posting.",
        examples=["https://jobs.example.com/positions/data-engineer"],
    )

    @field_validator("url")
    @classmethod
    def reject_local_or_private_urls(
        cls,
        url: HttpUrl,
    ) -> HttpUrl:
        """Reject obvious local and private destinations."""

        host = url.host

        if not host:
            raise ValueError("The URL must include a hostname.")

        normalized_host = host.lower().rstrip(".")

        if (
            normalized_host in BLOCKED_HOSTNAMES
            or normalized_host.endswith(".localhost")
            or normalized_host.endswith(".local")
        ):
            raise ValueError("Local URLs are not allowed.")

        try:
            address = ip_address(normalized_host)
        except ValueError:
            return url

        if not address.is_global:
            raise ValueError("Private or local IP addresses are not allowed.")

        return url


class JobUrlValidationResponse(BaseModel):
    """Successful URL-validation response."""

    valid: bool
    normalized_url: str
    hostname: str
    scheme: str


class JobPageFetchResponse(BaseModel):
    """Metadata returned after retrieving a job page."""

    fetched: bool
    source_url: str
    final_url: str
    status_code: int
    content_type: str
    bytes_downloaded: int
    redirect_count: int
    content_sha256: str


class JobRequirements(BaseModel):
    """Structured requirements requested by a job posting."""

    required_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Technical skills explicitly required from the candidate; "
            "exclude company stack and technologies mentioned only in "
            "descriptions or responsibilities."
        ),
    )
    preferred_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Technical skills explicitly marked optional, preferred, "
            "desirable, bonus, or nice to have."
        ),
    )
    qualifications: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit degrees, certifications, licences, experience, "
            "academic or professional background, theoretical knowledge, "
            "and formal eligibility criteria."
        ),
    )
    soft_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Interpersonal or behavioural abilities explicitly requested "
            "from the candidate; never infer them from responsibilities."
        ),
    )
    languages: list[str] = Field(
        default_factory=list,
        description=(
            "Spoken or written human languages explicitly required from the candidate."
        ),
    )

    @field_validator(
        "required_skills",
        "preferred_skills",
        "qualifications",
        "soft_skills",
        "languages",
        mode="before",
    )
    @classmethod
    def normalize_string_lists(
        cls,
        value: object,
    ) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            value = [value]

        if not isinstance(value, list):
            raise ValueError("Requirements must be provided as a list.")

        normalized: list[str] = []
        seen: set[str] = set()

        for item in value:
            if not isinstance(item, str):
                continue

            cleaned = repair_utf8_mojibake(" ".join(item.split()))

            if not cleaned:
                continue

            comparison_key = cleaned.casefold()

            if comparison_key in seen:
                continue

            seen.add(comparison_key)
            normalized.append(cleaned)

        return normalized

    @model_validator(mode="after")
    def remove_required_preferred_overlap(
        self,
    ) -> "JobRequirements":
        """
        A required skill must not also appear as preferred.
        """

        required_keys = {_skill_comparison_key(skill) for skill in self.required_skills}

        self.preferred_skills = [
            skill
            for skill in self.preferred_skills
            if _skill_comparison_key(skill) not in required_keys
        ]

        return self


class ExtractedJobPosting(BaseModel):
    """Structured information extracted from a job posting."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    title: str = Field(
        min_length=1,
    )
    company: str | None = None
    location: str | None = None
    description: str | None = None
    employment_types: list[str] = Field(default_factory=list)
    requirements: JobRequirements = Field(default_factory=JobRequirements)
    date_posted: str | None = None
    valid_through: str | None = None
    application_url: str

    @field_validator(
        "title",
        "company",
        "location",
        "description",
        "date_posted",
        "valid_through",
        mode="before",
    )
    @classmethod
    def blank_optional_values_to_none(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, str):
            cleaned = repair_utf8_mojibake(value.strip())
            return cleaned or None

        return value

    @field_validator(
        "employment_types",
        mode="before",
    )
    @classmethod
    def normalize_employment_types(
        cls,
        value: object,
    ) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            value = [value]

        if not isinstance(value, list):
            raise ValueError("Employment types must be a list.")

        return list(
            dict.fromkeys(
                repair_utf8_mojibake(item.strip())
                for item in value
                if isinstance(item, str) and item.strip()
            )
        )

    @model_validator(mode="after")
    def ensure_useful_content(
        self,
    ) -> "ExtractedJobPosting":
        useful_optional_fields = [
            self.company,
            self.location,
            self.description,
            self.employment_types,
        ]

        if not any(useful_optional_fields):
            raise ValueError(
                "The extracted job does not contain enough useful information."
            )

        return self


class GenericJobContent(BaseModel):
    """Content and metadata extracted from a generic job page."""

    page_title: str | None = None
    text: str = Field(min_length=200)
    source_url: str
    metadata: dict[str, str] = Field(default_factory=dict)


class JobExtractionResponse(BaseModel):
    """Successful structured job-extraction response."""

    extracted: bool
    extraction_method: str
    job: ExtractedJobPosting


class StoredJobResponse(BaseModel):
    """A job posting persisted in the database."""

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    source_url: str
    final_url: str
    application_url: str
    content_sha256: str
    title: str
    company: str | None
    location: str | None
    latitude: float | None
    longitude: float | None
    description: str | None
    employment_types: list[str]
    required_skills: list[str]
    preferred_skills: list[str]
    qualifications: list[str]
    soft_skills: list[str]
    languages: list[str]
    date_posted: str | None
    valid_through: str | None
    created_at: datetime
    extraction_method: str


class JobImportResponse(BaseModel):
    """Result of importing a job posting."""

    created: bool
    job: StoredJobResponse


class CandidateLanguage(BaseModel):
    """a spoken language and the candidate's proficiency level"""

    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1)
    level: str | None = None

    @field_validator("level", mode="before")
    @classmethod
    def blank_level_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = repair_utf8_mojibake(value.strip())
            return cleaned or None
        return value


class CandidateProfileInput(BaseModel):
    """Candidate profile input for job matching."""

    model_config = ConfigDict(str_strip_whitespace=True)
    full_name: str = Field(min_length=1)
    headline: str | None = None
    location: str | None = None
    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
    )
    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
    )
    max_commute_distance_km: float = Field(
        default=30,
        ge=0,
        le=500,
    )
    years_of_experience: float | None = Field(
        default=None,
        ge=0,
    )

    skills: list[str] = Field(
        default_factory=list,
    )
    languages: list[CandidateLanguage] = Field(
        default_factory=list,
    )
    preferred_locations: list[str] = Field(
        default_factory=list,
    )
    preferred_employment_types: list[str] = Field(
        default_factory=list,
    )

    @field_validator(
        "headline",
        "location",
        mode="before",
    )
    @classmethod
    def blank_optional_strings_to_none(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, str):
            return value.strip() or None

        return value

    @field_validator(
        "skills",
        "preferred_locations",
        "preferred_employment_types",
        mode="before",
    )
    @classmethod
    def normalize_string_lists(
        cls,
        value: object,
    ) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            value = [value]

        if not isinstance(value, list):
            raise ValueError("The value must be a list of strings.")

        normalized: list[str] = []
        seen: set[str] = set()

        for item in value:
            if not isinstance(item, str):
                continue

            cleaned = " ".join(item.split())

            if not cleaned:
                continue

            comparison_key = cleaned.casefold()

            if comparison_key in seen:
                continue

            seen.add(comparison_key)
            normalized.append(cleaned)

        return normalized


class CandidateProfileResponse(CandidateProfileInput):
    """Stored candidate profile returned by the API."""

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    created_at: datetime
    updated_at: datetime


class MatchCategoryBreakdown(BaseModel):
    """Score details for one matching category."""

    score: float = Field(ge=0)
    maximum: float = Field(ge=0)
    available: bool


class JobMatchResponse(BaseModel):
    """Explainable comparison between a job and candidate."""

    job_id: int
    profile_id: int
    score: int = Field(ge=0, le=100)
    recommendation: str

    matching_required_skills: list[str] = Field(
        default_factory=list,
    )
    missing_required_skills: list[str] = Field(
        default_factory=list,
    )
    matching_preferred_skills: list[str] = Field(
        default_factory=list,
    )
    missing_preferred_skills: list[str] = Field(
        default_factory=list,
    )

    location_match: bool | None = None
    location_distance_km: float | None = Field(
        default=None,
        ge=0,
    )
    maximum_commute_distance_km: float = Field(ge=0)
    location_match_method: str
    employment_type_match: bool | None = None

    breakdown: dict[
        str,
        MatchCategoryBreakdown,
    ]


def _skill_comparison_key(
    value: str,
) -> str:
    """Create a basic key for duplicate detection."""

    return " ".join(value.casefold().split())


class ApplicationStatus(StrEnum):
    SAVED = "saved"
    PREPARING = "preparing"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ApplicationEventType(StrEnum):
    STATUS_CHANGED = "status_changed"
    APPLIED = "applied"
    FOLLOW_UP_SENT = "follow_up_sent"
    EMPLOYER_RESPONSE = "employer_response"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTION = "rejection"
    NOTE_ADDED = "note_added"


class JobApplicationInput(BaseModel):
    """Create or update tracking information for a job."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    status: ApplicationStatus
    applied_at: date | None = None
    follow_up_at: date | None = None
    next_action: str | None = None
    notes: str | None = None

    @field_validator(
        "next_action",
        "notes",
        mode="before",
    )
    @classmethod
    def blank_strings_to_none(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, str):
            return value.strip() or None

        return value


class ApplicationEventInput(BaseModel):
    """A dated event in an application's history."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    event_type: ApplicationEventType
    occurred_at: datetime | None = None
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def blank_notes_to_none(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, str):
            return value.strip() or None

        return value


class ApplicationEventResponse(BaseModel):
    """An event returned in an application's history."""

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    event_type: ApplicationEventType
    occurred_at: datetime
    notes: str | None
    created_at: datetime


class JobApplicationResponse(BaseModel):
    """Stored application with provisional ghosting information."""

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    job_id: int
    status: ApplicationStatus

    applied_at: date | None
    follow_up_at: date | None
    last_follow_up_sent_at: datetime | None
    last_activity_at: datetime
    last_employer_response_at: datetime | None

    next_action: str | None
    notes: str | None

    days_without_response: int | None
    possibly_ghosted: bool
    ghosting_threshold_days: int

    events: list[ApplicationEventResponse] = Field(
        default_factory=list,
    )

    created_at: datetime
    updated_at: datetime


class ApplicationListItemResponse(BaseModel):
    """Compact application summary for the tracking list."""

    application_id: int
    job_id: int
    job_title: str
    company: str | None

    status: ApplicationStatus
    applied_at: date | None
    follow_up_at: date | None
    last_follow_up_sent_at: datetime | None

    last_activity_at: datetime
    last_employer_response_at: datetime | None

    next_action: str | None

    days_without_response: int | None
    possibly_ghosted: bool
    ghosting_threshold_days: int
