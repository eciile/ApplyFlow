from ipaddress import ip_address

from pydantic import BaseModel, Field, HttpUrl, field_validator


BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
}


class JobUrlRequest(BaseModel):
    """Request body used to validate a job-posting URL."""

    url: HttpUrl = Field(
        description="Public HTTP or HTTPS URL of a job posting.",
        examples=["https://jobs.example.com/positions/data-engineer"],
    )

    @field_validator("url")
    @classmethod
    def reject_local_or_private_urls(cls, url: HttpUrl) -> HttpUrl:
        """
        Reject obvious local and private-network destinations.

        Full network-level protection will also be added later when the
        application starts downloading pages.
        """
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
            # The host is a domain name rather than an IP address.
            return url

        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValueError("Private or local IP addresses are not allowed.")

        return url


class JobUrlValidationResponse(BaseModel):
    """Successful URL-validation response."""

    valid: bool
    normalized_url: str
    hostname: str
    scheme: str