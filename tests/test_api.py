from collections.abc import Generator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.database import Base, get_session
from app.main import app
from app.schemas import (
    ApplicationStatus,
    ExtractedJobPosting,
    JobRequirements,
)
from app.services.application_tracking import (
    assess_possible_ghosting,
)
from app.services.job_page_fetcher import (
    FetchedJobPage,
    UnsupportedContentTypeError,
)
from app.services.job_sources import JobExtractionResult

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

    app.dependency_overrides[get_session] = override_get_session

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert response.headers["content-type"] == ("application/json; charset=utf-8")


def test_valid_job_url() -> None:
    response = client.post(
        "/jobs/validate",
        json={"url": ("https://jobs.example.com/positions/data-engineer")},
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
        json={"url": "https://jobs.example.com/jobs/123"},
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
            "Expected an HTML page but received 'application/pdf'."
        )

    monkeypatch.setattr(
        main_module,
        "fetch_job_page",
        fake_fetch_job_page,
    )

    response = client.post(
        "/jobs/fetch",
        json={"url": "https://jobs.example.com/job.pdf"},
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

    class FakeLlmClient:
        async def extract_requirements(
            self,
            *,
            title: str,
            description: str,
        ) -> JobRequirements:
            assert title == "Junior Data Engineer"
            assert description == "Build reliable pipelines."
            return JobRequirements(
                required_skills=["Python", "SQL"],
                preferred_skills=["Docker"],
                qualifications=["Bachelor's degree"],
                soft_skills=["Communication"],
                languages=["English"],
            )

    monkeypatch.setattr(
        main_module,
        "get_llm_job_extraction_client",
        lambda: FakeLlmClient(),
    )

    response = client.post(
        "/jobs/extract",
        json={"url": "https://jobs.example.com/jobs/123"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["extracted"] is True
    assert data["extraction_method"] == "json_ld"

    job = data["job"]

    assert job["title"] == "Junior Data Engineer"
    assert job["company"] == "Example Company"
    assert job["location"] == ("Paris, Ile-de-France, 75001, FR")
    assert job["description"] == ("Build reliable pipelines.")
    assert job["employment_types"] == [
        "FULL_TIME",
        "PERMANENT",
    ]
    assert job["date_posted"] == "2026-07-20"
    assert job["valid_through"] == "2026-08-20"
    assert job["requirements"] == {
        "required_skills": ["Python", "SQL"],
        "preferred_skills": ["Docker"],
        "qualifications": ["Bachelor's degree"],
        "soft_skills": ["Communication"],
        "languages": ["English"],
    }


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
        json={"url": "https://jobs.example.com/jobs/123"},
    )

    assert response.status_code == 422
    assert "useful job information" in (response.json()["detail"])


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
        bytes_downloaded=len(html.encode("utf-8")),
        redirect_count=0,
        content_sha256="a" * 64,
    )


def _import_application_test_job(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str = "https://example.com/jobs/application-test",
) -> dict:
    """Import one deterministic job for application endpoint tests."""

    async def fake_retrieve_job_page(
        source_url: str,
    ) -> FetchedJobPage:
        return _fake_page(
            url=source_url,
            html="<html><body>job</body></html>",
        )

    async def fake_extract_structured_job(
        source_url: str,
    ) -> JobExtractionResult:
        return JobExtractionResult(
            job=ExtractedJobPosting(
                title="AI Engineer",
                company="Example Company",
                description="Build AI systems.",
                application_url=source_url,
            ),
            extraction_method="json_ld",
            final_url=source_url,
            content_sha256="e" * 64,
        )

    monkeypatch.setattr(
        main_module,
        "_retrieve_job_page",
        fake_retrieve_job_page,
    )
    monkeypatch.setattr(
        main_module,
        "_extract_structured_job",
        fake_extract_structured_job,
    )

    response = client.post(
        "/jobs/import",
        json={"url": url},
    )
    assert response.status_code == 201

    return response.json()["job"]


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

    class FakeLlmClient:
        async def extract_requirements(
            self,
            *,
            title: str,
            description: str,
        ) -> JobRequirements:
            assert title == "Junior Data Engineer"
            assert description == "Build data pipelines."
            return JobRequirements(
                required_skills=["Python", "SQL"],
                preferred_skills=["Docker"],
                qualifications=["Bachelor's degree"],
                soft_skills=["Communication"],
                languages=["English"],
            )

    monkeypatch.setattr(
        main_module,
        "get_llm_job_extraction_client",
        lambda: FakeLlmClient(),
    )

    request_body = {"url": "https://jobs.example.com/jobs/123"}

    first_response = client.post(
        "/jobs/import",
        json=request_body,
    )

    assert first_response.status_code == 201
    assert first_response.json()["created"] is True

    first_job = first_response.json()["job"]

    assert first_job["title"] == "Junior Data Engineer"
    assert first_job["company"] == "Example Company"
    assert first_job["employment_types"] == ["FULL_TIME"]
    assert first_job["extraction_method"] == "json_ld"

    second_response = client.post(
        "/jobs/import",
        json=request_body,
    )

    assert second_response.status_code == 200
    assert second_response.json()["created"] is False
    assert second_response.json()["job"]["id"] == first_job["id"]

    list_response = client.get("/jobs")

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    jobs = list_response.json()

    assert jobs[0]["required_skills"] == ["Python", "SQL"]
    assert jobs[0]["preferred_skills"] == ["Docker"]
    assert jobs[0]["qualifications"] == ["Bachelor's degree"]
    assert jobs[0]["soft_skills"] == ["Communication"]
    assert jobs[0]["languages"] == ["English"]


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
        json={"url": ("https://job-boards.greenhouse.io/example/jobs/12345")},
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
                description=("Develop and maintain reliable data pipelines."),
                employment_types=["FULL_TIME"],
                date_posted=None,
                valid_through=None,
                application_url=content.source_url,
            )

        async def extract_requirements(
            self,
            *,
            title: str,
            description: str,
        ) -> JobRequirements:
            assert title == "Junior Data Engineer"
            assert description == ("Develop and maintain reliable data pipelines.")
            return JobRequirements(
                required_skills=["Python", "SQL", "REST API"],
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
        json={"url": ("https://company.example.com/careers/junior-data-engineer")},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["extracted"] is True
    assert data["extraction_method"] == "llm_html"
    assert data["job"]["title"] == "Junior Data Engineer"
    assert data["job"]["company"] == "Example Company"
    assert data["job"]["location"] == "Paris, France"
    assert data["job"]["requirements"]["required_skills"] == [
        "Python",
        "SQL",
        "REST API",
    ]


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
                description=("Build and maintain reliable data pipelines."),
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
                    qualifications=[
                        "Bachelor's degree",
                    ],
                    soft_skills=[
                        "Teamwork",
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
        json={"url": ("https://company.example.com/careers/junior-data-engineer")},
    )

    assert response.status_code == 201

    data = response.json()

    assert data["created"] is True
    assert data["job"]["title"] == "Junior Data Engineer"
    assert data["job"]["company"] == "Example Company"
    assert data["job"]["employment_types"] == ["FULL_TIME"]
    assert data["job"]["extraction_method"] == "llm_html"

    list_response = client.get("/jobs")

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["extraction_method"] == "llm_html"
    assert data["job"]["required_skills"] == [
        "Python",
        "SQL",
        "FastAPI",
    ]
    assert data["job"]["preferred_skills"] == [
        "Docker",
        "AWS",
    ]
    assert data["job"]["qualifications"] == [
        "Bachelor's degree",
    ]
    assert data["job"]["soft_skills"] == ["Teamwork"]
    assert data["job"]["languages"] == [
        "French",
        "English",
    ]


def test_get_candidate_profile_returns_404_when_missing(
    isolated_database,
) -> None:
    with TestClient(app) as client:
        response = client.get("/profile")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Candidate profile not found.",
    }


def test_put_candidate_profile_creates_and_updates_single_profile(
    isolated_database,
) -> None:
    with TestClient(app) as client:
        create_response = client.put(
            "/profile",
            json={
                "full_name": "Test Candidate",
                "headline": "Computer Engineering Graduate",
                "location": "Rennes, France",
                "years_of_experience": 1,
                "skills": [
                    "Python",
                    "FastAPI",
                    " python ",
                    "",
                ],
                "languages": [
                    {
                        "name": "French",
                        "level": "Professional",
                    },
                    {
                        "name": "English",
                        "level": "Fluent",
                    },
                ],
                "preferred_locations": [
                    "Rennes",
                    "Remote",
                    "rennes",
                    "",
                ],
                "preferred_employment_types": [
                    "PERMANENT",
                ],
            },
        )

        assert create_response.status_code == 200

        created_profile = create_response.json()

        update_response = client.put(
            "/profile",
            json={
                "full_name": "Updated Candidate",
                "headline": "Junior AI Engineer",
                "location": "Paris, France",
                "years_of_experience": 2,
                "skills": [
                    "Python",
                    "PyTorch",
                    "NLP",
                ],
                "languages": [
                    {
                        "name": "French",
                        "level": "Professional",
                    },
                ],
                "preferred_locations": [
                    "Paris",
                    "Remote",
                ],
                "preferred_employment_types": [
                    "PERMANENT",
                ],
            },
        )

        get_response = client.get("/profile")

    assert created_profile["id"] == 1
    assert created_profile["skills"] == [
        "Python",
        "FastAPI",
    ]
    assert created_profile["preferred_locations"] == [
        "Rennes",
        "Remote",
    ]

    assert update_response.status_code == 200

    updated_profile = update_response.json()

    assert updated_profile["id"] == created_profile["id"]
    assert updated_profile["full_name"] == "Updated Candidate"
    assert updated_profile["skills"] == [
        "Python",
        "PyTorch",
        "NLP",
    ]

    assert get_response.status_code == 200
    assert get_response.json()["id"] == created_profile["id"]
    assert get_response.json()["full_name"] == "Updated Candidate"


def test_match_geocodes_and_caches_missing_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://example.com/jobs/rennes-engineer"

    async def fake_retrieve_job_page(
        source_url: str,
    ) -> FetchedJobPage:
        return _fake_page(
            url=source_url,
            html="<html><body>job</body></html>",
        )

    async def fake_extract_structured_job(
        source_url: str,
    ) -> JobExtractionResult:
        return JobExtractionResult(
            job=ExtractedJobPosting(
                title="Software Engineer",
                company="Example",
                location="Rennes, France",
                description="Build software in Rennes.",
                employment_types=["PERMANENT"],
                requirements=JobRequirements(
                    qualifications=["Master's degree"],
                    soft_skills=["Leadership"],
                ),
                application_url=source_url,
            ),
            extraction_method="json_ld",
            final_url=source_url,
            content_sha256="c" * 64,
        )

    geocoding_calls: list[str] = []

    def fake_geocode_location(
        location: str,
    ) -> tuple[float, float]:
        geocoding_calls.append(location)
        coordinates = {
            "Cesson-Sévigné, France": (48.1212, -1.6030),
            "Rennes, France": (48.1109, -1.6837),
        }
        return coordinates[location]

    monkeypatch.setattr(
        main_module,
        "_retrieve_job_page",
        fake_retrieve_job_page,
    )
    monkeypatch.setattr(
        main_module,
        "_extract_structured_job",
        fake_extract_structured_job,
    )
    monkeypatch.setattr(
        main_module,
        "geocode_location",
        fake_geocode_location,
    )

    profile_response = client.put(
        "/profile",
        json={
            "full_name": "Test Candidate",
            "location": "Cesson-Sévigné, France",
            "preferred_employment_types": ["PERMANENT"],
        },
    )
    import_response = client.post(
        "/jobs/import",
        json={"url": url},
    )

    assert profile_response.status_code == 200
    assert import_response.status_code == 201

    first_match = client.post("/jobs/1/match")
    second_match = client.post("/jobs/1/match")

    assert first_match.status_code == 200
    result = first_match.json()
    assert result["score"] == 100
    assert result["location_match"] is True
    assert result["location_distance_km"] is not None
    assert result["location_distance_km"] < 10
    assert result["location_match_method"] == "distance"
    assert second_match.status_code == 200
    assert geocoding_calls == [
        "Cesson-Sévigné, France",
        "Rennes, France",
    ]


def test_application_reports_latest_completed_follow_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://example.com/jobs/follow-up-test"

    async def fake_retrieve_job_page(
        source_url: str,
    ) -> FetchedJobPage:
        return _fake_page(
            url=source_url,
            html="<html><body>job</body></html>",
        )

    async def fake_extract_structured_job(
        source_url: str,
    ) -> JobExtractionResult:
        return JobExtractionResult(
            job=ExtractedJobPosting(
                title="AI Engineer",
                company="Example",
                description="Build AI systems.",
                application_url=source_url,
            ),
            extraction_method="json_ld",
            final_url=source_url,
            content_sha256="d" * 64,
        )

    monkeypatch.setattr(
        main_module,
        "_retrieve_job_page",
        fake_retrieve_job_page,
    )
    monkeypatch.setattr(
        main_module,
        "_extract_structured_job",
        fake_extract_structured_job,
    )

    import_response = client.post(
        "/jobs/import",
        json={"url": url},
    )
    assert import_response.status_code == 201

    create_response = client.put(
        "/jobs/1/application",
        json={
            "status": "applied",
            "follow_up_at": "2026-08-10",
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["last_follow_up_sent_at"] is None

    for occurred_at in (
        "2026-08-03T09:00:00+00:00",
        "2026-08-04T16:50:23.651947+00:00",
    ):
        event_response = client.post(
            "/jobs/1/application/events",
            json={
                "event_type": "follow_up_sent",
                "occurred_at": occurred_at,
            },
        )
        assert event_response.status_code == 201

    update_response = client.put(
        "/jobs/1/application",
        json={
            "status": "interview",
            "follow_up_at": None,
        },
    )
    assert update_response.status_code == 200

    application = update_response.json()
    assert application["follow_up_at"] is None
    assert application["last_follow_up_sent_at"].startswith(
        "2026-08-04T16:50:23.651947"
    )

    list_response = client.get("/applications")
    assert list_response.status_code == 200
    listed_application = list_response.json()[0]
    assert listed_application["follow_up_at"] is None
    assert listed_application["last_follow_up_sent_at"].startswith(
        "2026-08-04T16:50:23.651947"
    )


def test_put_application_creates_then_updates_single_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _import_application_test_job(monkeypatch)
    endpoint = f"/jobs/{job['id']}/application"

    create_response = client.put(
        endpoint,
        json={
            "status": "preparing",
            "follow_up_at": "2026-08-12",
            "next_action": "Tailor cover letter",
            "notes": "Initial tracking note",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["job_id"] == job["id"]
    assert created["status"] == "preparing"
    assert created["follow_up_at"] == "2026-08-12"
    assert len(created["events"]) == 1

    update_response = client.put(
        endpoint,
        json={
            "status": "applied",
            "applied_at": "2026-08-04",
            "follow_up_at": "2026-08-11",
            "next_action": "Send follow-up",
            "notes": "Application submitted",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["id"] == created["id"]
    assert updated["status"] == "applied"
    assert updated["applied_at"] == "2026-08-04"
    assert updated["next_action"] == "Send follow-up"
    assert len(updated["events"]) == 2

    list_response = client.get("/applications")
    assert list_response.status_code == 200
    applications = list_response.json()
    assert len(applications) == 1
    assert applications[0]["application_id"] == created["id"]
    assert applications[0]["job_id"] == job["id"]
    assert applications[0]["job_title"] == "AI Engineer"
    assert applications[0]["company"] == "Example Company"
    assert applications[0]["status"] == "applied"


def test_employer_response_clears_provisional_ghosting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _import_application_test_job(monkeypatch)
    endpoint = f"/jobs/{job['id']}/application"

    create_response = client.put(
        endpoint,
        json={
            "status": "applied",
            "applied_at": "2000-01-01",
        },
    )
    assert create_response.status_code == 200
    before_response = create_response.json()
    assert before_response["possibly_ghosted"] is True
    assert before_response["days_without_response"] >= 21

    event_response = client.post(
        f"{endpoint}/events",
        json={
            "event_type": "employer_response",
            "occurred_at": "2026-08-04T12:30:00+00:00",
            "notes": "Recruiter scheduled a screening call.",
        },
    )
    assert event_response.status_code == 201
    after_response = event_response.json()
    assert after_response["possibly_ghosted"] is False
    assert after_response["days_without_response"] is None
    assert after_response["last_employer_response_at"].startswith("2026-08-04T12:30:00")
    employer_response_events = [
        event
        for event in after_response["events"]
        if event["event_type"] == "employer_response"
    ]
    assert len(employer_response_events) == 1
    assert employer_response_events[0]["occurred_at"].startswith("2026-08-04T12:30:00")


def test_application_endpoints_distinguish_missing_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_job_response = client.put(
        "/jobs/999/application",
        json={"status": "saved"},
    )
    assert missing_job_response.status_code == 404
    assert missing_job_response.json() == {"detail": "Job not found."}

    job = _import_application_test_job(monkeypatch)

    missing_application_response = client.get(f"/jobs/{job['id']}/application")
    assert missing_application_response.status_code == 404
    assert missing_application_response.json() == {
        "detail": "Job application not found."
    }

    missing_application_event_response = client.post(
        f"/jobs/{job['id']}/application/events",
        json={"event_type": "follow_up_sent"},
    )
    assert missing_application_event_response.status_code == 404
    assert missing_application_event_response.json() == {
        "detail": "Job application not found."
    }


def test_provisional_ghosting_starts_at_twenty_one_days() -> None:
    before_threshold = assess_possible_ghosting(
        status="applied",
        applied_at=date(2026, 7, 15),
        last_employer_response_at=None,
        current_date=date(2026, 8, 4),
    )
    at_threshold = assess_possible_ghosting(
        status="applied",
        applied_at=date(2026, 7, 14),
        last_employer_response_at=None,
        current_date=date(2026, 8, 4),
    )

    assert before_threshold.days_without_response == 20
    assert before_threshold.possibly_ghosted is False
    assert at_threshold.days_without_response == 21
    assert at_threshold.possibly_ghosted is True
    assert at_threshold.ghosting_threshold_days == 21


def test_employer_response_prevents_ghosting_flag() -> None:
    assessment = assess_possible_ghosting(
        status=ApplicationStatus.APPLIED,
        applied_at=date(2026, 7, 1),
        last_employer_response_at=datetime(
            2026,
            7,
            15,
            10,
            0,
            tzinfo=UTC,
        ),
        current_date=date(2026, 8, 1),
    )

    assert assessment.days_without_response is None
    assert assessment.possibly_ghosted is False


def test_interview_status_is_not_possibly_ghosted() -> None:
    assessment = assess_possible_ghosting(
        status=ApplicationStatus.INTERVIEW,
        applied_at=date(2026, 7, 1),
        last_employer_response_at=None,
        current_date=date(2026, 8, 1),
    )

    assert assessment.days_without_response == 31
    assert assessment.possibly_ghosted is False
