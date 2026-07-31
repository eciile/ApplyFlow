from ipaddress import ip_address
from datetime import datetime
from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    field_validator,
    ConfigDict,
)

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
}


class JobUrlRequest(BaseModel):
    """Request body containing a job-posting URL."""

    url: HttpUrl = Field(
        description="Public HTTP or HTTPS URL of a job posting.",
        examples=[
            "https://jobs.example.com/positions/data-engineer"
        ],
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
            raise ValueError(
                "The URL must include a hostname."
            )

        normalized_host = host.lower().rstrip(".")

        if (
            normalized_host in BLOCKED_HOSTNAMES
            or normalized_host.endswith(".localhost")
            or normalized_host.endswith(".local")
        ):
            raise ValueError(
                "Local URLs are not allowed."
            )

        try:
            address = ip_address(normalized_host)
        except ValueError:
            return url

        if not address.is_global:
            raise ValueError(
                "Private or local IP addresses are not allowed."
            )

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


class ExtractedJobPosting(BaseModel):
    """Structured information extracted from JobPosting JSON-LD."""

    title: str
    company: str | None = None
    location: str | None = None
    description: str | None = None
    employment_types: list[str] = Field(
        default_factory=list
    )
    date_posted: str | None = None
    valid_through: str | None = None
    application_url: str


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
    description: str | None
    employment_types: list[str]
    date_posted: str | None
    valid_through: str | None
    created_at: datetime


class JobImportResponse(BaseModel):
    """Result of importing a job posting."""

    created: bool
    job: StoredJobResponse