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
                "positions/data-engineer?source=linkedin"
            )
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["valid"] is True
    assert data["hostname"] == "jobs.example.com"
    assert data["scheme"] == "https"
    assert data["normalized_url"] == (
        "https://jobs.example.com/"
        "positions/data-engineer?source=linkedin"
    )


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
        return FetchedJobPage(
            source_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            html="<html><body>Data Engineer</body></html>",
            bytes_downloaded=46,
            redirect_count=0,
            content_sha256="a" * 64,
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
    assert data["redirect_count"] == 0
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
    assert response.json()["detail"] == (
        "Expected an HTML page but received "
        "'application/pdf'."
    )