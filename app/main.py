from fastapi import (
    FastAPI,
    HTTPException,
    status,
    Depends,
    Response,
    Request,
)
from app.schemas import (
    JobPageFetchResponse,
    JobUrlRequest,
    JobUrlValidationResponse,
    JobExtractionResponse,
    JobImportResponse,
    StoredJobResponse,
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
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Job
from app.services.job_sources import (
    JobExtractionResult,
    JobSourceError,
    JobSourceNotFoundError,
    extract_ats_job,
)
from app.services.generic_html_extractor import (
    GenericContentExtractionError,
    extract_generic_job_content,
)
from app.services.llm_job_extractor import (
    LlmJobExtractionError,
    get_llm_job_extraction_client,
)

app = FastAPI(
    title="ApplyFlow API",
    description=(
        "A personal job-search assistant that imports job postings "
        "from URLs and evaluates their relevance and risk."
    ),
    version="0.2.0",
)


@app.middleware("http")
async def add_utf8_charset_to_json(
    request: Request,
    call_next,
):
    """Help legacy clients decode JSON responses as UTF-8."""

    response = await call_next(request)
    content_type = response.headers.get("content-type", "")

    if content_type.casefold() == "application/json":
        response.headers["content-type"] = (
            "application/json; charset=utf-8"
        )

    return response


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

async def _extract_structured_job(
    url: str,
) -> JobExtractionResult:
    """
    Extract a job through an ATS adapter or JSON-LD fallback.
    """

    try:
        ats_result = await extract_ats_job(url)

    except JobSourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    except JobSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if ats_result is not None:
        return ats_result

    page = await _retrieve_job_page(url)

    try:
        job = extract_job_posting_jsonld(
            html=page.html,
            source_url=page.final_url,
        )
    except JobPostingNotFoundError:
        # The page has no usable JobPosting JSON-LD.
        # Continue with the generic HTML and LLM fallback.
        pass
    else:
        return JobExtractionResult(
            job=job,
            extraction_method="json_ld",
            final_url=page.final_url,
            content_sha256=page.content_sha256,
        )

    try:
        generic_content = extract_generic_job_content(
            html=page.html,
            source_url=page.final_url,
        )
    except GenericContentExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    llm_client = get_llm_job_extraction_client()

    try:
        job = await llm_client.extract_job(
            generic_content
        )
    except LlmJobExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return JobExtractionResult(
        job=job,
        extraction_method="llm_html",
        final_url=page.final_url,
        content_sha256=page.content_sha256,
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
    """Extract a job through an ATS adapter or JSON-LD."""

    result = await _extract_structured_job(
        str(payload.url)
    )

    return JobExtractionResponse(
        extracted=True,
        extraction_method=result.extraction_method,
        job=result.job,
    )

@app.post(
    "/jobs/import",
    response_model=JobImportResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Jobs"],
)
async def import_job(
    payload: JobUrlRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> JobImportResponse:
    """
    Fetch, extract, and persist a job posting.

    Importing the same normalized source URL more than once
    returns the existing record.
    """

    source_url = str(payload.url)

    existing_job = session.scalar(
        select(Job).where(
            Job.source_url == source_url
        )
    )

    if existing_job is not None:
        response.status_code = status.HTTP_200_OK

        return JobImportResponse(
            created=False,
            job=StoredJobResponse.model_validate(
                existing_job
            ),
        )

    page = await _retrieve_job_page(source_url)

    try:
        result = await _extract_structured_job(source_url)
        extracted_job = result.job
    except JobPostingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    job = Job(
        source_url=source_url,
        final_url=result.final_url,
        application_url=extracted_job.application_url,
        content_sha256=result.content_sha256,
        extraction_method=result.extraction_method,
        title=extracted_job.title,
        company=extracted_job.company,
        location=extracted_job.location,
        description=extracted_job.description,
        employment_types=extracted_job.employment_types,
        required_skills=(
            extracted_job.requirements.required_skills
        ),
        preferred_skills=(
            extracted_job.requirements.preferred_skills
        ),
        languages=extracted_job.requirements.languages,
        date_posted=extracted_job.date_posted,
        valid_through=extracted_job.valid_through,
    )

    session.add(job)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()

        existing_job = session.scalar(
            select(Job).where(
                Job.source_url == source_url
            )
        )

        if existing_job is None:
            raise

        response.status_code = status.HTTP_200_OK

        return JobImportResponse(
            created=False,
            job=StoredJobResponse.model_validate(
                existing_job
            ),
        )

    session.refresh(job)

    return JobImportResponse(
        created=True,
        job=StoredJobResponse.model_validate(job),
    )


@app.get(
    "/jobs",
    response_model=list[StoredJobResponse],
    tags=["Jobs"],
)
def list_jobs(
    session: Session = Depends(get_session),
) -> list[StoredJobResponse]:
    """Return every imported job, newest first."""

    jobs = session.scalars(
        select(Job).order_by(
            Job.created_at.desc()
        )
    ).all()

    return [
        StoredJobResponse.model_validate(job)
        for job in jobs
    ]
