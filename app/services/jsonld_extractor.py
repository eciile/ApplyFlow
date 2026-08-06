from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from bs4 import BeautifulSoup

from app.schemas import ExtractedJobPosting

JSON_LD_CONTENT_TYPE = "application/ld+json"


class JobPostingNotFoundError(ValueError):
    """Raised when HTML contains no usable JobPosting JSON-LD."""


def extract_job_posting_jsonld(
    html: str,
    source_url: str,
) -> ExtractedJobPosting:
    """
    Extract the first usable Schema.org JobPosting object.

    Malformed JSON-LD blocks are ignored because pages may contain
    several unrelated structured-data scripts.
    """

    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script"):
        script_type = script.get("type")

        if not isinstance(script_type, str):
            continue

        normalized_type = script_type.split(";", maxsplit=1)[0].strip().lower()

        if normalized_type != JSON_LD_CONTENT_TYPE:
            continue

        raw_json = script.string or script.get_text()

        if not raw_json or not raw_json.strip():
            continue

        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        for node in _walk_json(payload):
            if not _is_job_posting(node):
                continue

            job = _build_job_posting(
                node=node,
                source_url=source_url,
            )

            if job is not None:
                return job

    raise JobPostingNotFoundError("No usable JobPosting JSON-LD was found on the page.")


def _walk_json(value: Any) -> Iterator[dict[str, Any]]:
    """
    Recursively visit dictionaries inside JSON-LD.

    This supports:
    - One JSON-LD object
    - A list of objects
    - Objects nested inside @graph
    """

    if isinstance(value, dict):
        yield value

        for nested_value in value.values():
            if isinstance(nested_value, (dict, list)):
                yield from _walk_json(nested_value)

    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def _is_job_posting(node: dict[str, Any]) -> bool:
    """Return whether a JSON-LD node represents JobPosting."""

    raw_types = node.get("@type")

    if isinstance(raw_types, str):
        types = [raw_types]
    elif isinstance(raw_types, list):
        types = raw_types
    else:
        return False

    return any(
        _normalize_schema_type(value) == "jobposting"
        for value in types
        if isinstance(value, str)
    )


def _normalize_schema_type(value: str) -> str:
    """Normalize common JSON-LD type representations."""

    normalized = value.strip().rstrip("/")

    normalized = normalized.rsplit("/", maxsplit=1)[-1]
    normalized = normalized.rsplit("#", maxsplit=1)[-1]
    normalized = normalized.rsplit(":", maxsplit=1)[-1]

    return normalized.lower()


def _build_job_posting(
    node: dict[str, Any],
    source_url: str,
) -> ExtractedJobPosting | None:
    """Convert one JSON-LD node into our API schema."""

    title = _clean_text(node.get("title") or node.get("name"))

    if not title:
        return None

    location = _extract_location(node.get("jobLocation"))

    if location is None and _is_remote_job(node.get("jobLocationType")):
        location = "Remote"

    application_url = _plain_string(node.get("url")) or source_url

    return ExtractedJobPosting(
        title=title,
        company=_extract_company(node.get("hiringOrganization")),
        location=location,
        description=_clean_text(node.get("description")),
        employment_types=_string_list(node.get("employmentType")),
        date_posted=_plain_string(node.get("datePosted")),
        valid_through=_plain_string(node.get("validThrough")),
        application_url=application_url,
    )


def _extract_company(value: Any) -> str | None:
    """Extract the hiring organization's name."""

    if isinstance(value, str):
        return _clean_text(value)

    if isinstance(value, dict):
        return _clean_text(value.get("name") or value.get("legalName"))

    if isinstance(value, list):
        for organization in value:
            company = _extract_company(organization)

            if company:
                return company

    return None


def _extract_location(value: Any) -> str | None:
    """Convert Schema.org Place or PostalAddress values to text."""

    if isinstance(value, str):
        return _clean_text(value)

    if isinstance(value, list):
        locations = [
            location for item in value if (location := _extract_location(item))
        ]

        unique_locations = list(dict.fromkeys(locations))

        return " | ".join(unique_locations) or None

    if not isinstance(value, dict):
        return None

    address = value.get("address")

    if isinstance(address, str):
        return _clean_text(address)

    if isinstance(address, dict):
        country = address.get("addressCountry")

        if isinstance(country, dict):
            country = country.get("name") or country.get("identifier")

        parts = [
            _plain_string(address.get("streetAddress")),
            _plain_string(address.get("addressLocality")),
            _plain_string(address.get("addressRegion")),
            _plain_string(address.get("postalCode")),
            _plain_string(country),
        ]

        cleaned_parts = [part for part in parts if part]

        if cleaned_parts:
            return ", ".join(cleaned_parts)

    return _clean_text(value.get("name"))


def _is_remote_job(value: Any) -> bool:
    """Detect Schema.org TELECOMMUTE job-location values."""

    return any(item.upper() == "TELECOMMUTE" for item in _string_list(value))


def _string_list(value: Any) -> list[str]:
    """Normalize a string or list of strings."""

    if isinstance(value, str):
        cleaned = _clean_text(value)
        return [cleaned] if cleaned else []

    if isinstance(value, list):
        values: list[str] = []

        for item in value:
            cleaned = _clean_text(item)

            if cleaned:
                values.append(cleaned)

        return list(dict.fromkeys(values))

    return []


def _plain_string(value: Any) -> str | None:
    """Return a stripped string without HTML processing."""

    if value is None:
        return None

    text = str(value).strip()

    return text or None


def _clean_text(value: Any) -> str | None:
    """Strip HTML tags and normalize whitespace."""

    text = _plain_string(value)

    if text is None:
        return None

    return BeautifulSoup(
        text,
        "html.parser",
    ).get_text(
        separator=" ",
        strip=True,
    )
