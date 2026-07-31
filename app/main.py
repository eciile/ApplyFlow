from fastapi import FastAPI, HTTPException, status

from app.schemas import (
    JobPageFetchResponse,
    JobUrlRequest,
    JobUrlValidationResponse,
    JobExtractionResponse,
)
from app.services.job_page_fetcher import (
    FetchedJobPage,
    JobPageConnectionError,
    JobPageFetchError,
    JobPageHttpError,
    JobPageTimeoutError,
    PageTooLargeError,
    RedirectError,
    UnsupportedContentTypeError,
    fetch_job_page,
)
from app.services.jsonld_extractor import (
    JobPostingNotFoundError,
    extract_job_posting_jsonld,
)
from app.services.url_security import UnsafeUrlError

app = FastAPI(
    title="ApplyFlow API",
    description=(
        "A personal job-search assistant that imports job postings "
        "from URLs and evaluates their relevance and risk."
    ),
    version="0.2.0",
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
    """Validate and normalize a job-posting URL."""

    host = payload.url.host

    if host is None:
        raise ValueError(
            "Validated URL unexpectedly has no hostname."
        )

    return JobUrlValidationResponse(
        valid=True,
        normalized_url=str(payload.url),
        hostname=host,
        scheme=payload.url.scheme,
    )


async def _retrieve_job_page(
    url: str,
) -> FetchedJobPage:
    """Retrieve a page and convert service errors to API errors."""

    try:
        return await fetch_job_page(url)

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

    page = await _retrieve_job_page(
        str(payload.url)
    )

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


@app.post(
    "/jobs/extract",
    response_model=JobExtractionResponse,
    status_code=status.HTTP_200_OK,
    tags=["Jobs"],
)
async def extract_job_from_url(
    payload: JobUrlRequest,
) -> JobExtractionResponse:
    """Retrieve a job URL and extract JobPosting JSON-LD."""

    page = await _retrieve_job_page(
        str(payload.url)
    )

    try:
        job = extract_job_posting_jsonld(
            html=page.html,
            source_url=page.final_url,
        )
    except JobPostingNotFoundError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return JobExtractionResponse(
        extracted=True,
        extraction_method="json_ld",
        job=job,
    )