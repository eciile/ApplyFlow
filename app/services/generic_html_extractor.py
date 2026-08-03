from __future__ import annotations
from bs4 import BeautifulSoup
from pydantic import ValidationError
from trafilatura import extract
from app.schemas import GenericJobContent

METADATA_LABELS = {
    "filiale": "company",
    "entreprise": "company",
    "société": "company",
    "company": "company",
    "employer": "company",
    "contrat": "contract",
    "type de contrat": "contract",
    "contract": "contract",
    "localisation": "location",
    "lieu": "location",
    "location": "location",
    "référence": "reference",
    "reference": "reference",
}

class GenericContentExtractionError(ValueError):
    """"raised when useful content cannot be extracted from html"""

def extract_generic_job_content(
        html:str,
        source_url:str,
) -> GenericJobContent:
    """Extracts readable content from a generic job page."""
    if not html.strip():
        raise GenericContentExtractionError(
            "The job page contains no HTML content."
        )
    soup=BeautifulSoup(html, "html.parser")
    page_title=_extract_page_title(soup)
    metadata = _extract_page_metadata(soup)
    extracted_text = extract(
        html,
        output_format="txt",
        include_comments=False,
        include_tables=False,
        include_links=False,
        favor_precision=True,
    )
    if extracted_text is None:
        raise GenericContentExtractionError(
            "The extracted page does not contain enough useful job information."
        )
    cleaned_text = _normalize_text(extracted_text)
    try:
        return GenericJobContent(
            page_title=page_title,
            text=cleaned_text,
            source_url=source_url,
            metadata=metadata,
        )
    except ValidationError as exc:
        raise GenericContentExtractionError(
            "The extracted page does not contain enough useful job information."
        ) from exc

GENERIC_TITLE_MARKERS = {
    "détails offre",
    "detail offre",
    "job details",
    "offre d'emploi",
    "offres d'emploi",
    "careers",
    "carrières",
    "recrutement",
    "jobs",
}


def _extract_page_title(
    soup: BeautifulSoup,
) -> str | None:
    """
    Find a role-specific title.

    Prefer visible headings and social metadata over the
    generic HTML document title.
    """

    candidates: list[str] = []

    for selector in (
        "h1",
        '[role="heading"][aria-level="1"]',
        ".job-title",
        ".offer-title",
        ".titre-offre",
    ):
        element = soup.select_one(selector)

        if element is not None:
            candidates.append(
                element.get_text(
                    separator=" ",
                    strip=True,
                )
            )

    for attributes in (
        {"property": "og:title"},
        {"name": "twitter:title"},
    ):
        element = soup.find("meta", attrs=attributes)

        if element is not None:
            content = element.get("content")

            if isinstance(content, str):
                candidates.append(content)

    if soup.title is not None:
        candidates.append(
            soup.title.get_text(
                separator=" ",
                strip=True,
            )
        )

    for candidate in candidates:
        cleaned = _normalize_optional_text(candidate)

        if cleaned and not _is_generic_page_title(cleaned):
            return cleaned

    return None


def _is_generic_page_title(title: str) -> bool:
    normalized = title.casefold()

    return any(
        marker in normalized
        for marker in GENERIC_TITLE_MARKERS
    )


def _extract_page_metadata(
    soup: BeautifulSoup,
) -> dict[str, str]:
    """Extract values displayed beside common job metadata labels."""

    metadata: dict[str, str] = {}

    for element in soup.find_all(
        ["dt", "th", "p", "span", "div"]
    ):
        label = _normalize_optional_text(
            element.get_text(" ", strip=True)
        )

        if label is None:
            continue

        key = METADATA_LABELS.get(
            label.casefold().rstrip(":")
        )

        if key is None or key in metadata:
            continue

        value = _find_metadata_value(element)

        if value is not None:
            metadata[key] = value

    return metadata


def _find_metadata_value(element: object) -> str | None:
    """Find a nearby sibling containing a metadata label's value."""

    current = element

    for _ in range(3):
        sibling = getattr(
            current,
            "find_next_sibling",
            lambda: None,
        )()

        while sibling is not None:
            value = _normalize_optional_text(
                sibling.get_text(" ", strip=True)
            )

            if value is not None:
                return value

            sibling = sibling.find_next_sibling()

        current = getattr(current, "parent", None)

        if current is None:
            break

    return None


def _normalize_text(value: str) -> str:
    """Normalize whitespace while preserving paragraphs."""

    paragraphs = [
        " ".join(paragraph.split())
        for paragraph in value.splitlines()
        if paragraph.strip()
    ]

    return "\n".join(paragraphs)


def _normalize_optional_text(
    value: str,
) -> str | None:
    cleaned = " ".join(value.split())

    return cleaned or None
