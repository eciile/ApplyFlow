import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.services.job_page_fetcher import (
    FetchedJobPage,
    UnsupportedContentTypeError,
)


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


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


def test_extract_returns_422_without_jobposting(
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
    assert response.json()["detail"] == (
        "No usable JobPosting JSON-LD was found "
        "on the page."
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