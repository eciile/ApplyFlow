from ipaddress import ip_address
from datetime import datetime
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
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
    employment_types: list[str] = Field(
        default_factory=list
    )
    date_posted: str | None = None
    valid_through: str | None = None
    application_url: str

    @field_validator(
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
            cleaned = value.strip()
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
            raise ValueError(
                "Employment types must be a list."
            )

        return list(
            dict.fromkeys(
                item.strip()
                for item in value
                if isinstance(item, str)
                and item.strip()
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
                "The extracted job does not contain "
                "enough useful information."
            )

        return self

class GenericJobContent(BaseModel):
    """Content and metadata extracted from a generic job page."""

    page_title: str | None = None
    text: str = Field(min_length=200)
    source_url: str
    metadata: dict[str, str] = Field(
        default_factory=dict
    )

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
    extraction_method: str


class JobImportResponse(BaseModel):
    """Result of importing a job posting."""

    created: bool
    job: StoredJobResponse
