import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.services.job_page_fetcher import (
    FetchedJobPage,
    UnsupportedContentTypeError,
)
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.schemas import ExtractedJobPosting, JobRequirements
from app.services.job_sources import JobExtractionResult
from types import SimpleNamespace

client = TestClient(app)

@pytest.fixture(autouse=True)
def isolated_database() -> Generator[None, None, None]:
    """Use a fresh in-memory SQLite database per test."""

    test_engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    testing_session = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(test_engine)

    def override_get_session():
        with testing_session() as session:
            yield session

    app.dependency_overrides[
        get_session
    ] = override_get_session

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()

def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert response.headers["content-type"] == (
        "application/json; charset=utf-8"
    )


def test_valid_job_url() -> None:
    response = client.post(
        "/jobs/validate",
        json={
            "url": (
                "https://jobs.example.com/"
                "positions/data-engineer"
            )
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["valid"] is True
    assert data["hostname"] == "jobs.example.com"
    assert data["scheme"] == "https"


@pytest.mark.parametrize(
    "invalid_url",
    [
        "not-a-url",
        "linkedin.com/jobs/123",
        "ftp://example.com/job",
        "http://127.0.0.1/jobs",
        "http://192.168.1.10/jobs",
    ],
)
def test_invalid_or_private_job_url(
    invalid_url: str,
) -> None:
    response = client.post(
        "/jobs/validate",
        json={"url": invalid_url},
    )

    assert response.status_code == 422


def test_fetch_job_page_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_job_page(
        url: str,
    ) -> FetchedJobPage:
        return _fake_page(
            url=url,
            html="<html><body>Data Engineer</body></html>",
        )

    monkeypatch.setattr(
        main_module,
        "fetch_job_page",
        fake_fetch_job_page,
    )

    response = client.post(
        "/jobs/fetch",
        json={
            "url": "https://jobs.example.com/jobs/123"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["fetched"] is True
    assert data["status_code"] == 200
    assert data["content_type"] == "text/html"
    assert data["content_sha256"] == "a" * 64


def test_fetch_endpoint_rejects_non_html_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_job_page(
        url: str,
    ) -> FetchedJobPage:
        raise UnsupportedContentTypeError(
            "Expected an HTML page but received "
            "'application/pdf'."
        )

    monkeypatch.setattr(
        main_module,
        "fetch_job_page",
        fake_fetch_job_page,
    )

    response = client.post(
        "/jobs/fetch",
        json={
            "url": "https://jobs.example.com/job.pdf"
        },
    )

    assert response.status_code == 415


def test_extract_job_posting_jsonld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@graph": [
            {
              "@type": "Organization",
              "name": "Example organization"
            },
            {
              "@type": "JobPosting",
              "title": "Junior Data Engineer",
              "description": "<p>Build reliable pipelines.</p>",
              "datePosted": "2026-07-20",
              "validThrough": "2026-08-20",
              "employmentType": ["FULL_TIME", "PERMANENT"],
              "hiringOrganization": {
                "@type": "Organization",
                "name": "Example Company"
              },
              "jobLocation": {
                "@type": "Place",
                "address": {
                  "@type": "PostalAddress",
                  "addressLocality": "Paris",
                  "addressRegion": "Ile-de-France",
                  "postalCode": "75001",
                  "addressCountry": "FR"
                }
              },
              "url": "https://jobs.example.com/jobs/123"
            }
          ]
        }
        </script>
      </head>
    </html>
    """

    async def fake_fetch_job_page(
        url: str,
    ) -> FetchedJobPage:
        return _fake_page(
            url=url,
            html=html,
        )

    monkeypatch.setattr(
        main_module,
        "fetch_job_page",
        fake_fetch_job_page,
    )

    response = client.post(
        "/jobs/extract",
        json={
            "url": "https://jobs.example.com/jobs/123"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["extracted"] is True
    assert data["extraction_method"] == "json_ld"

    job = data["job"]

    assert job["title"] == "Junior Data Engineer"
    assert job["company"] == "Example Company"
    assert job["location"] == (
        "Paris, Ile-de-France, 75001, FR"
    )
    assert job["description"] == (
        "Build reliable pipelines."
    )
    assert job["employment_types"] == [
        "FULL_TIME",
        "PERMANENT",
    ]
    assert job["date_posted"] == "2026-07-20"
    assert job["valid_through"] == "2026-08-20"


def test_extract_returns_422_without_usable_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "WebSite",
          "name": "Example Careers"
        }
        </script>
      </head>
    </html>
    """

    async def fake_fetch_job_page(
        url: str,
    ) -> FetchedJobPage:
        return _fake_page(
            url=url,
            html=html,
        )

    monkeypatch.setattr(
        main_module,
        "fetch_job_page",
        fake_fetch_job_page,
    )

    response = client.post(
        "/jobs/extract",
        json={
            "url": "https://jobs.example.com/jobs/123"
        },
    )

    assert response.status_code == 422
    assert "useful job information" in (
        response.json()["detail"]
    )


def _fake_page(
    url: str,
    html: str,
) -> FetchedJobPage:
    """Create a page fixture without network access."""

    return FetchedJobPage(
        source_url=url,
        final_url=url,
        status_code=200,
        content_type="text/html",
        html=html,
        bytes_downloaded=len(
            html.encode("utf-8")
        ),
        redirect_count=0,
        content_sha256="a" * 64,
    )

def test_import_job_is_saved_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Junior Data Engineer",
          "description": "<p>Build data pipelines.</p>",
          "employmentType": "FULL_TIME",
          "hiringOrganization": {
            "@type": "Organization",
            "name": "Example Company"
          },
          "jobLocation": {
            "@type": "Place",
            "address": {
              "@type": "PostalAddress",
              "addressLocality": "Paris",
              "addressCountry": "FR"
            }
          },
          "url": "https://jobs.example.com/jobs/123"
        }
        </script>
      </head>
    </html>
    """

    async def fake_fetch_job_page(
        url: str,
    ) -> FetchedJobPage:
        return _fake_page(
            url=url,
            html=html,
        )

    monkeypatch.setattr(
        main_module,
        "fetch_job_page",
        fake_fetch_job_page,
    )

    request_body = {
        "url": "https://jobs.example.com/jobs/123"
    }

    first_response = client.post(
        "/jobs/import",
        json=request_body,
    )

    assert first_response.status_code == 201
    assert first_response.json()["created"] is True

    first_job = first_response.json()["job"]

    assert first_job["title"] == "Junior Data Engineer"
    assert first_job["company"] == "Example Company"
    assert first_job["employment_types"] == [
        "FULL_TIME"
    ]
    assert first_job["extraction_method"] == "json_ld"

    second_response = client.post(
        "/jobs/import",
        json=request_body,
    )

    assert second_response.status_code == 200
    assert second_response.json()["created"] is False
    assert (
        second_response.json()["job"]["id"]
        == first_job["id"]
    )

    list_response = client.get("/jobs")

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    jobs = list_response.json()

    assert jobs[0]["required_skills"] == []
    assert jobs[0]["preferred_skills"] == []
    assert jobs[0]["languages"] == []
def test_extract_endpoint_uses_greenhouse_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_extract_ats_job(
        url: str,
    ) -> JobExtractionResult:
        return JobExtractionResult(
            job=ExtractedJobPosting(
                title="Junior Data Engineer",
                company="Example Company",
                location="Paris, France",
                description="Build reliable data pipelines.",
                employment_types=[],
                requirements=JobRequirements(
                required_skills=[
                    "Python",
                    "SQL",
                    "FastAPI",
                ],
                preferred_skills=[
                    "Docker",
                    "AWS",
                ],
                languages=[
                    "French",
                    "English",
                ],
            ),
                date_posted=None,
                valid_through=None,
                application_url=url,
            ),
            extraction_method="greenhouse",
            final_url=url,
            content_sha256="b" * 64,
        )

    monkeypatch.setattr(
        main_module,
        "extract_ats_job",
        fake_extract_ats_job,
    )

    response = client.post(
        "/jobs/extract",
        json={
            "url": (
                "https://job-boards.greenhouse.io/"
                "example/jobs/12345"
            )
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["extraction_method"] == "greenhouse"
    assert data["job"]["title"] == "Junior Data Engineer"
    assert data["job"]["company"] == "Example Company"

def test_extract_uses_llm_for_generic_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <html>
      <head>
        <title>
          Junior Data Engineer | Example Company
        </title>
      </head>
      <body>
        <main>
          <h1>Junior Data Engineer</h1>

          <p>
            Example Company is looking for a Junior Data
            Engineer to develop and maintain reliable Python
            and SQL data pipelines for analytics applications.
          </p>

          <p>
            The role involves data-quality validation,
            automated testing, API integration, database
            development, and collaboration with engineering
            and analytics teams.
          </p>

          <p>
            This is a full-time position based in Paris,
            France. Candidates should have experience with
            Python, SQL, relational databases, and REST APIs.
          </p>
        </main>
      </body>
    </html>
    """

    async def fake_fetch_job_page(
        url: str,
    ) -> FetchedJobPage:
        return _fake_page(
            url=url,
            html=html,
        )

    class FakeLlmClient:
        async def extract_job(
            self,
            content,
        ) -> ExtractedJobPosting:
            assert "Junior Data Engineer" in content.text

            return ExtractedJobPosting(
                title="Junior Data Engineer",
                company="Example Company",
                location="Paris, France",
                description=(
                    "Develop and maintain reliable data pipelines."
                ),
                employment_types=["FULL_TIME"],
                date_posted=None,
                valid_through=None,
                application_url=content.source_url,
            )

    monkeypatch.setattr(
        main_module,
        "fetch_job_page",
        fake_fetch_job_page,
    )

    monkeypatch.setattr(
        main_module,
        "get_llm_job_extraction_client",
        lambda: FakeLlmClient(),
    )

    response = client.post(
        "/jobs/extract",
        json={
            "url": (
                "https://company.example.com/"
                "careers/junior-data-engineer"
            )
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["extracted"] is True
    assert data["extraction_method"] == "llm_html"
    assert data["job"]["title"] == "Junior Data Engineer"
    assert data["job"]["company"] == "Example Company"
    assert data["job"]["location"] == "Paris, France"

def test_import_persists_llm_extracted_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <html>
      <head>
        <title>
          Junior Data Engineer | Example Company
        </title>
      </head>
      <body>
        <main>
          <h1>Junior Data Engineer</h1>

          <p>
            Example Company is hiring a Junior Data Engineer
            in Paris, France. This is a full-time role.
          </p>

          <p>
            The candidate will build Python and SQL pipelines,
            integrate APIs, validate data quality, write tests,
            and collaborate with engineering teams.
          </p>

          <p>
            Applicants should have experience with relational
            databases, Git, Docker, and data-processing systems.
          </p>
        </main>
      </body>
    </html>
    """

    async def fake_fetch_job_page(
        url: str,
    ) -> FetchedJobPage:
        return _fake_page(
            url=url,
            html=html,
        )

    class FakeLlmClient:
        async def extract_job(
            self,
            content,
        ) -> ExtractedJobPosting:
            return ExtractedJobPosting(
                title="Junior Data Engineer",
                company="Example Company",
                location="Paris, France",
                description=(
                    "Build and maintain reliable data pipelines."
                ),
                employment_types=["FULL_TIME"],
                requirements=JobRequirements(
                    required_skills=[
                        "Python",
                        "SQL",
                        "FastAPI",
                    ],
                    preferred_skills=[
                        "Docker",
                        "AWS",
                    ],
                    languages=[
                        "French",
                        "English",
                    ],
                ),
                date_posted=None,
                valid_through=None,
                application_url=content.source_url,
            )

    monkeypatch.setattr(
        main_module,
        "fetch_job_page",
        fake_fetch_job_page,
    )

    monkeypatch.setattr(
        main_module,
        "get_llm_job_extraction_client",
        lambda: FakeLlmClient(),
    )

    response = client.post(
        "/jobs/import",
        json={
            "url": (
                "https://company.example.com/"
                "careers/junior-data-engineer"
            )
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["created"] is True
    assert data["job"]["title"] == "Junior Data Engineer"
    assert data["job"]["company"] == "Example Company"
    assert data["job"]["employment_types"] == [
        "FULL_TIME"
    ]
    assert data["job"]["extraction_method"] == "llm_html"

    list_response = client.get("/jobs")

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert (
        list_response.json()[0]["extraction_method"]
        == "llm_html"
    )
    assert data["job"]["required_skills"] == [
        "Python",
        "SQL",
        "FastAPI",
    ]
    assert data["job"]["preferred_skills"] == [
        "Docker",
        "AWS",
    ]
    assert data["job"]["languages"] == [
        "French",
        "English",
    ]
