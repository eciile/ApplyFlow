from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from html import unescape
from typing import Any
from urllib.parse import quote, urlsplit

import httpx2
from bs4 import BeautifulSoup

from app.schemas import ExtractedJobPosting


class JobSource(StrEnum):
    """Supported job-posting sources."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    GENERIC = "generic"


GREENHOUSE_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
}

LEVER_HOSTS = {
    "jobs.lever.co",
    "jobs.eu.lever.co",
}


@dataclass(frozen=True, slots=True)
class GreenhouseReference:
    """Values identifying a Greenhouse job posting."""

    board_token: str
    job_id: str


@dataclass(frozen=True, slots=True)
class LeverReference:
    """Values identifying a Lever job posting."""

    site: str
    posting_id: str
    api_host: str


@dataclass(frozen=True, slots=True)
class JobExtractionResult:
    """Normalized result returned by a job extractor."""

    job: ExtractedJobPosting
    extraction_method: str
    final_url: str
    content_sha256: str


class JobSourceError(Exception):
    """Raised when a job source cannot return usable data."""


class JobSourceNotFoundError(JobSourceError):
    """Raised when a job posting no longer exists."""


def detect_job_source(url: str) -> JobSource:
    """Identify the platform hosting a job posting."""

    parsed_url = urlsplit(url)
    hostname = (parsed_url.hostname or "").lower()

    if hostname in GREENHOUSE_HOSTS:
        return JobSource.GREENHOUSE

    if hostname in LEVER_HOSTS:
        return JobSource.LEVER

    return JobSource.GENERIC


def parse_greenhouse_url(
    url: str,
) -> GreenhouseReference | None:
    """
    Extract the board token and job ID from a Greenhouse URL.

    Expected format:
    https://job-boards.greenhouse.io/{board}/jobs/{job_id}
    """

    if detect_job_source(url) != JobSource.GREENHOUSE:
        return None

    parsed_url = urlsplit(url)

    path_parts = [part for part in parsed_url.path.split("/") if part]

    if len(path_parts) < 3:
        return None

    board_token, jobs_segment, job_id = path_parts[:3]

    if jobs_segment.lower() != "jobs":
        return None

    if not board_token:
        return None

    if not job_id.isdigit():
        return None

    return GreenhouseReference(
        board_token=board_token,
        job_id=job_id,
    )


def parse_lever_url(
    url: str,
) -> LeverReference | None:
    """
    Extract the site and posting ID from a Lever URL.

    Supported formats:
    https://jobs.lever.co/{site}/{posting_id}
    https://jobs.eu.lever.co/{site}/{posting_id}
    """

    if detect_job_source(url) != JobSource.LEVER:
        return None

    parsed_url = urlsplit(url)
    hostname = (parsed_url.hostname or "").lower()

    path_parts = [part for part in parsed_url.path.split("/") if part]

    if len(path_parts) < 2:
        return None

    site, posting_id = path_parts[:2]

    if not site or not posting_id:
        return None

    api_host = "api.eu.lever.co" if hostname == "jobs.eu.lever.co" else "api.lever.co"

    return LeverReference(
        site=site,
        posting_id=posting_id,
        api_host=api_host,
    )


async def fetch_greenhouse_job(
    reference: GreenhouseReference,
    source_url: str,
    client: httpx2.AsyncClient | None = None,
) -> ExtractedJobPosting:
    """Retrieve and normalize one Greenhouse job posting."""

    board_token = quote(
        reference.board_token,
        safe="",
    )
    job_id = quote(
        reference.job_id,
        safe="",
    )

    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}"

    owns_client = client is None

    if client is None:
        client = httpx2.AsyncClient(
            timeout=httpx2.Timeout(10.0),
            follow_redirects=False,
            trust_env=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "JobMatch/0.3",
            },
        )

    try:
        response = await client.get(api_url)

        if response.status_code == 404:
            raise JobSourceNotFoundError(
                "The Greenhouse job was not found or is no longer published."
            )

        response.raise_for_status()
        payload = response.json()

    except JobSourceError:
        raise

    except httpx2.TimeoutException as exc:
        raise JobSourceError("Greenhouse took too long to respond.") from exc

    except httpx2.HTTPStatusError as exc:
        raise JobSourceError(
            f"Greenhouse returned HTTP status {exc.response.status_code}."
        ) from exc

    except httpx2.RequestError as exc:
        raise JobSourceError("Greenhouse could not be reached.") from exc

    except ValueError as exc:
        raise JobSourceError("Greenhouse returned invalid JSON.") from exc

    finally:
        if owns_client:
            await client.aclose()

    if not isinstance(payload, dict):
        raise JobSourceError("Greenhouse returned an unexpected response.")

    title = _clean_text(payload.get("title"))

    if not title:
        raise JobSourceError("The Greenhouse response did not contain a job title.")

    location_data = payload.get("location")
    location: str | None = None

    if isinstance(location_data, dict):
        location = _clean_text(location_data.get("name"))

    application_url = _clean_text(payload.get("absolute_url")) or source_url

    return ExtractedJobPosting(
        title=title,
        company=_clean_text(payload.get("company_name")),
        location=location,
        description=_clean_html(payload.get("content")),
        employment_types=[],
        date_posted=_clean_text(payload.get("first_published")),
        valid_through=_clean_text(payload.get("application_deadline")),
        application_url=application_url,
    )


def _clean_text(value: Any) -> str | None:
    """Return a normalized string value."""

    if not isinstance(value, str):
        return None

    cleaned = " ".join(value.split())

    return cleaned or None


def _clean_html(value: Any) -> str | None:
    """Decode and remove HTML from a Greenhouse field."""

    if not isinstance(value, str):
        return None

    decoded = unescape(unescape(value))

    cleaned = BeautifulSoup(
        decoded,
        "html.parser",
    ).get_text(
        separator=" ",
        strip=True,
    )

    normalized = " ".join(cleaned.split())

    return normalized or None


async def fetch_lever_job(
    reference: LeverReference,
    source_url: str,
    client: httpx2.AsyncClient | None = None,
) -> ExtractedJobPosting:
    """Retrieve and normalize one Lever job posting."""

    site = quote(
        reference.site,
        safe="",
    )
    posting_id = quote(
        reference.posting_id,
        safe="",
    )

    api_url = f"https://{reference.api_host}/v0/postings/{site}/{posting_id}"

    owns_client = client is None

    if client is None:
        client = httpx2.AsyncClient(
            timeout=httpx2.Timeout(10.0),
            follow_redirects=False,
            trust_env=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "JobMatch/0.3",
            },
        )

    try:
        response = await client.get(api_url)

        if response.status_code == 404:
            raise JobSourceNotFoundError(
                "The Lever job was not found or is no longer published."
            )

        response.raise_for_status()
        payload = response.json()

    except JobSourceError:
        raise

    except httpx2.TimeoutException as exc:
        raise JobSourceError("Lever took too long to respond.") from exc

    except httpx2.HTTPStatusError as exc:
        raise JobSourceError(
            f"Lever returned HTTP status {exc.response.status_code}."
        ) from exc

    except httpx2.RequestError as exc:
        raise JobSourceError("Lever could not be reached.") from exc

    except ValueError as exc:
        raise JobSourceError("Lever returned invalid JSON.") from exc

    finally:
        if owns_client:
            await client.aclose()

    if not isinstance(payload, dict):
        raise JobSourceError("Lever returned an unexpected response.")

    title = _clean_text(payload.get("text"))

    if not title:
        raise JobSourceError("The Lever response did not contain a job title.")

    categories = payload.get("categories")

    if not isinstance(categories, dict):
        categories = {}

    location = _clean_text(categories.get("location"))

    country = _clean_text(payload.get("country"))

    if location and country:
        if country.lower() not in location.lower():
            location = f"{location}, {country}"
    elif country:
        location = country

    commitment = _clean_text(categories.get("commitment"))

    employment_types = [commitment] if commitment else []

    description = _clean_text(payload.get("descriptionPlain")) or _clean_html(
        payload.get("description")
    )

    hosted_url = _clean_text(payload.get("hostedUrl"))

    application_url = _clean_text(payload.get("applyUrl")) or hosted_url or source_url

    return ExtractedJobPosting(
        title=title,
        company=None,
        location=location,
        description=description,
        employment_types=employment_types,
        date_posted=None,
        valid_through=None,
        application_url=application_url,
    )


async def extract_ats_job(
    url: str,
    client: httpx2.AsyncClient | None = None,
) -> JobExtractionResult | None:
    """
    Extract a job through a supported ATS adapter.

    Return None for generic websites so the caller can use
    JSON-LD extraction instead.
    """

    source = detect_job_source(url)

    if source == JobSource.GREENHOUSE:
        reference = parse_greenhouse_url(url)

        if reference is None:
            raise JobSourceError("The Greenhouse job URL has an unsupported format.")

        job = await fetch_greenhouse_job(
            reference=reference,
            source_url=url,
            client=client,
        )

        return JobExtractionResult(
            job=job,
            extraction_method=JobSource.GREENHOUSE.value,
            final_url=url,
            content_sha256=_hash_job(job),
        )
    if source == JobSource.LEVER:
        reference = parse_lever_url(url)

        if reference is None:
            raise JobSourceError("The Lever job URL has an unsupported format.")

        job = await fetch_lever_job(
            reference=reference,
            source_url=url,
            client=client,
        )

        return JobExtractionResult(
            job=job,
            extraction_method=JobSource.LEVER.value,
            final_url=url,
            content_sha256=_hash_job(job),
        )

    return None


def _hash_job(job: ExtractedJobPosting) -> str:
    """Create a stable hash from normalized job information."""

    serialized_job = job.model_dump_json().encode("utf-8")

    return sha256(serialized_job).hexdigest()
