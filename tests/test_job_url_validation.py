import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_valid_https_job_url() -> None:
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


def test_valid_http_job_url() -> None:
    response = client.post(
        "/jobs/validate",
        json={"url": "http://careers.example.com/jobs/123"},
    )

    assert response.status_code == 200
    assert response.json()["scheme"] == "http"


@pytest.mark.parametrize(
    "invalid_url",
    [
        "not-a-url",
        "linkedin.com/jobs/123",
        "ftp://example.com/job",
        "file:///C:/jobs/example.html",
    ],
)
def test_invalid_url_is_rejected(invalid_url: str) -> None:
    response = client.post(
        "/jobs/validate",
        json={"url": invalid_url},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://localhost:8000/jobs",
        "http://localhost.localdomain/jobs",
        "http://127.0.0.1/jobs",
        "http://192.168.1.10/jobs",
        "http://10.0.0.1/jobs",
        "http://169.254.1.1/jobs",
    ],
)
def test_local_and_private_urls_are_rejected(
    blocked_url: str,
) -> None:
    response = client.post(
        "/jobs/validate",
        json={"url": blocked_url},
    )

    assert response.status_code == 422


def test_missing_url_is_rejected() -> None:
    response = client.post(
        "/jobs/validate",
        json={},
    )

    assert response.status_code == 422


def test_empty_request_body_is_rejected() -> None:
    response = client.post("/jobs/validate")

    assert response.status_code == 422