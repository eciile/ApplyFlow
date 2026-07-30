from fastapi import FastAPI, status

from app.schemas import JobUrlRequest, JobUrlValidationResponse


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