from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urljoin
import httpx2
from app.services.url_security import (
    UnsafeUrlError,
    ensure_public_url,
)

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3

ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}

REDIRECT_STATUS_CODES = {
    301,
    302,
    303,
    307,
    308,
}

REQUEST_HEADERS = {
    "User-Agent": (
        "ApplyFlow/0.1 "
        "(personal job-search assistant; contact: local-development)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en,fr;q=0.8",
}


class JobPageFetchError(Exception):
    """Base exception for job-page retrieval failures."""


class JobPageTimeoutError(JobPageFetchError):
    """Raised when the remote website takes too long to respond."""


class JobPageConnectionError(JobPageFetchError):
    """Raised when the remote website cannot be reached."""


class JobPageHttpError(JobPageFetchError):
    """Raised when the remote website returns an error status."""


class UnsupportedContentTypeError(JobPageFetchError):
    """Raised when the downloaded resource is not HTML."""


class PageTooLargeError(JobPageFetchError):
    """Raised when the downloaded HTML exceeds the allowed size."""


class RedirectError(JobPageFetchError):
    """Raised for invalid or excessive redirects."""


@dataclass(frozen=True, slots=True)
class FetchedJobPage:
    """Successfully downloaded job-page content."""

    source_url: str
    final_url: str
    status_code: int
    content_type: str
    html: str
    bytes_downloaded: int
    redirect_count: int
    content_sha256: str


def parse_content_length(value: str | None) -> int | None:
    """Convert a Content-Length header into an integer."""

    if value is None:
        return None

    try:
        parsed_value = int(value)
    except ValueError:
        return None

    return parsed_value if parsed_value >= 0 else None


async def fetch_job_page(
    url: str,
    client: httpx2.AsyncClient | None = None,
) -> FetchedJobPage:
    """
    Retrieve a public HTML page with security and size controls.

    A supplied client is useful for tests. In normal usage, this
    function creates and closes its own client.
    """

    owns_client = client is None

    if client is None:
        timeout = httpx2.Timeout(
            connect=5.0,
            read=10.0,
            write=5.0,
            pool=5.0,
        )

        limits = httpx2.Limits(
            max_connections=10,
            max_keepalive_connections=5,
        )

        client = httpx2.AsyncClient(
            timeout=timeout,
            limits=limits,
            follow_redirects=False,
            trust_env=False,
            headers=REQUEST_HEADERS,
        )

    try:
        return await _fetch_with_client(url, client)
    finally:
        if owns_client:
            await client.aclose()


async def _fetch_with_client(
    source_url: str,
    client: httpx2.AsyncClient,
) -> FetchedJobPage:
    current_url = source_url
    redirect_count = 0

    while True:
        # Run this check again after every redirect.
        await ensure_public_url(current_url)

        try:
            async with client.stream(
                "GET",
                current_url,
            ) as response:
                if response.status_code in REDIRECT_STATUS_CODES:
                    location = response.headers.get("location")

                    if not location:
                        raise RedirectError(
                            "The website returned a redirect "
                            "without a destination."
                        )

                    if redirect_count >= MAX_REDIRECTS:
                        raise RedirectError(
                            "The website returned too many redirects."
                        )

                    current_url = urljoin(
                        str(response.url),
                        location,
                    )
                    redirect_count += 1
                    continue

                try:
                    response.raise_for_status()
                except httpx2.HTTPStatusError as exc:
                    raise JobPageHttpError(
                        "The website returned HTTP status "
                        f"{response.status_code}."
                    ) from exc

                content_type_header = response.headers.get(
                    "content-type",
                    "",
                )

                content_type = (
                    content_type_header
                    .split(";", maxsplit=1)[0]
                    .strip()
                    .lower()
                )

                if content_type not in ALLOWED_CONTENT_TYPES:
                    displayed_type = content_type or "missing"

                    raise UnsupportedContentTypeError(
                        "Expected an HTML page but received "
                        f"'{displayed_type}'."
                    )

                declared_length = parse_content_length(
                    response.headers.get("content-length")
                )

                if (
                    declared_length is not None
                    and declared_length > MAX_RESPONSE_BYTES
                ):
                    raise PageTooLargeError(
                        "The page exceeds the 2 MB download limit."
                    )

                content = bytearray()

                async for chunk in response.aiter_bytes():
                    content.extend(chunk)

                    if len(content) > MAX_RESPONSE_BYTES:
                        raise PageTooLargeError(
                            "The page exceeds the 2 MB download limit."
                        )

                content_bytes = bytes(content)
                encoding = response.encoding or "utf-8"

                html = content_bytes.decode(
                    encoding,
                    errors="replace",
                )

                return FetchedJobPage(
                    source_url=source_url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=content_type,
                    html=html,
                    bytes_downloaded=len(content_bytes),
                    redirect_count=redirect_count,
                    content_sha256=sha256(
                        content_bytes
                    ).hexdigest(),
                )

        except (
            UnsafeUrlError,
            RedirectError,
            UnsupportedContentTypeError,
            PageTooLargeError,
            JobPageHttpError,
        ):
            raise
        except httpx2.TimeoutException as exc:
            raise JobPageTimeoutError(
                "The website took too long to respond."
            ) from exc
        except httpx2.RequestError as exc:
            raise JobPageConnectionError(
                "The website could not be reached."
            ) from exc