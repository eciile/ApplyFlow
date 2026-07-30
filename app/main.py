from fastapi import FastAPI, HTTPException, status

from app.schemas import (
    JobPageFetchResponse,
    JobUrlRequest,
    JobUrlValidationResponse,
)
from app.services.job_page_fetcher import (
    JobPageConnectionError,
    JobPageFetchError,
    JobPageHttpError,
    JobPageTimeoutError,
    PageTooLargeError,
    RedirectError,
    UnsupportedContentTypeError,
    fetch_job_page,
)
from app.services.url_security import UnsafeUrlError

app = FastAPI(
    title="ApplyFlow API",
    description=(
        "A personal job-search assistant that imports job postings "
        "from URLs and evaluates their relevance and risk."
    ),
    version="0.1.0",
)


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Return the current API status."""
    return {"status": "healthy"}


@app.post(
    "/jobs/validate",
    response_model=JobUrlValidationResponse,
    status_code=status.HTTP_200_OK,
    tags=["Jobs"],
)
def validate_job_url(
    payload: JobUrlRequest,
) -> JobUrlValidationResponse:
    """
    Validate and normalize a job-posting URL.

    This endpoint validates the URL format only. It does not download
    or verify the existence of the page yet.
    """
    host = payload.url.host

    # The schema already ensures that the URL has a host.
    if host is None:
        raise ValueError("Validated URL unexpectedly has no hostname.")

    return JobUrlValidationResponse(
        valid=True,
        normalized_url=str(payload.url),
        hostname=host,
        scheme=payload.url.scheme,
    )

@app.post(
    "/jobs/fetch",
    response_model=JobPageFetchResponse,
    status_code=status.HTTP_200_OK,
    tags=["Jobs"],
)
async def fetch_public_job_page(
    payload: JobUrlRequest,
) -> JobPageFetchResponse:
    """Safely retrieve a public HTML job page."""

    try:
        page = await fetch_job_page(str(payload.url))
    except UnsafeUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PageTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except UnsupportedContentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except JobPageTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except (
        JobPageConnectionError,
        JobPageHttpError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except RedirectError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except JobPageFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The job page could not be retrieved.",
        ) from exc

    return JobPageFetchResponse(
        fetched=True,
        source_url=page.source_url,
        final_url=page.final_url,
        status_code=page.status_code,
        content_type=page.content_type,
        bytes_downloaded=page.bytes_downloaded,
        redirect_count=page.redirect_count,
        content_sha256=page.content_sha256,
    )