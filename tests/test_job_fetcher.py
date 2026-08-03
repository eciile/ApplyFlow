import asyncio
import socket

import httpx2
import pytest

import app.services.job_page_fetcher as fetcher_module
import app.services.url_security as security_module
from app.services.job_page_fetcher import (
    PageTooLargeError,
    UnsupportedContentTypeError,
    fetch_job_page,
)
from app.services.url_security import (
    UnsafeUrlError,
    ensure_public_url,
)
from app.services.job_sources import (
    GreenhouseReference,
    JobSource,
    detect_job_source,
    parse_greenhouse_url,
    fetch_greenhouse_job,
    parse_lever_url,
    fetch_lever_job,
    LeverReference,
    extract_ats_job,
)
from app.services.generic_html_extractor import (
    GenericContentExtractionError,
    extract_generic_job_content,
)
from types import SimpleNamespace

from app.config import Settings
from app.schemas import GenericJobContent
from app.services.llm_job_extractor import (
    OllamaJobExtractionClient,
)

async def allow_mock_url(_: str) -> None:
    """
    Skip DNS validation in HTTP transport tests.

    These tests use a mock transport and never contact
    the real internet.
    """


def test_fetch_html_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fetcher_module,
        "ensure_public_url",
        allow_mock_url,
    )

    async def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        return httpx2.Response(
            status_code=200,
            headers={
                "Content-Type": "text/html; charset=utf-8"
            },
            content=(
                b"<html><body>"
                b"<h1>Data Engineer</h1>"
                b"</body></html>"
            ),
            request=request,
        )

    async def run_test():
        transport = httpx2.MockTransport(handler)

        async with httpx2.AsyncClient(
            transport=transport,
        ) as client:
            return await fetch_job_page(
                "https://jobs.example.com/jobs/123",
                client=client,
            )

    page = asyncio.run(run_test())

    assert page.status_code == 200
    assert page.content_type == "text/html"
    assert page.redirect_count == 0
    assert page.bytes_downloaded > 0
    assert "Data Engineer" in page.html
    assert len(page.content_sha256) == 64


def test_redirect_destination_is_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_urls: list[str] = []

    async def record_checked_url(url: str) -> None:
        checked_urls.append(url)

    monkeypatch.setattr(
        fetcher_module,
        "ensure_public_url",
        record_checked_url,
    )

    async def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        if request.url.host == "jobs.example.com":
            return httpx2.Response(
                status_code=302,
                headers={
                    "Location": (
                        "https://careers.example.org/jobs/123"
                    )
                },
                request=request,
            )

        return httpx2.Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>Job page</html>",
            request=request,
        )

    async def run_test():
        transport = httpx2.MockTransport(handler)

        async with httpx2.AsyncClient(
            transport=transport,
        ) as client:
            return await fetch_job_page(
                "https://jobs.example.com/jobs/123",
                client=client,
            )

    page = asyncio.run(run_test())

    assert page.redirect_count == 1
    assert page.final_url == (
        "https://careers.example.org/jobs/123"
    )

    assert checked_urls == [
        "https://jobs.example.com/jobs/123",
        "https://careers.example.org/jobs/123",
    ]


def test_non_html_content_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fetcher_module,
        "ensure_public_url",
        allow_mock_url,
    )

    async def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        return httpx2.Response(
            status_code=200,
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF",
            request=request,
        )

    async def run_test():
        transport = httpx2.MockTransport(handler)

        async with httpx2.AsyncClient(
            transport=transport,
        ) as client:
            return await fetch_job_page(
                "https://jobs.example.com/job.pdf",
                client=client,
            )

    with pytest.raises(UnsupportedContentTypeError):
        asyncio.run(run_test())


def test_oversized_page_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fetcher_module,
        "ensure_public_url",
        allow_mock_url,
    )

    async def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        return httpx2.Response(
            status_code=200,
            headers={
                "Content-Type": "text/html",
                "Content-Length": str(3 * 1024 * 1024),
            },
            request=request,
        )

    async def run_test():
        transport = httpx2.MockTransport(handler)

        async with httpx2.AsyncClient(
            transport=transport,
        ) as client:
            return await fetch_job_page(
                "https://jobs.example.com/jobs/large",
                client=client,
            )

    with pytest.raises(PageTooLargeError):
        asyncio.run(run_test())


def test_domain_resolving_to_private_ip_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 443),
            )
        ]

    monkeypatch.setattr(
        security_module.socket,
        "getaddrinfo",
        fake_getaddrinfo,
    )

    with pytest.raises(
        UnsafeUrlError,
        match="non-public IP",
    ):
        asyncio.run(
            ensure_public_url(
                "https://jobs.example.com/jobs/123"
            )
        )

@pytest.mark.parametrize(
    ("url", "expected_source"),
    [
        (
            "https://job-boards.greenhouse.io/example/jobs/12345",
            JobSource.GREENHOUSE,
        ),
        (
            "https://boards.greenhouse.io/example/jobs/12345",
            JobSource.GREENHOUSE,
        ),
        (
            "https://jobs.lever.co/example/posting-id",
            JobSource.LEVER,
        ),
        (
            "https://jobs.eu.lever.co/example/posting-id",
            JobSource.LEVER,
        ),
        (
            "https://company.example.com/careers/data-engineer",
            JobSource.GENERIC,
        ),
    ],
)
def test_detect_job_source(
    url: str,
    expected_source: JobSource,
) -> None:
    assert detect_job_source(url) == expected_source

@pytest.mark.parametrize(
    ("url", "expected_reference"),
    [
        (
            (
                "https://job-boards.greenhouse.io/"
                "example/jobs/12345"
            ),
            GreenhouseReference(
                board_token="example",
                job_id="12345",
            ),
        ),
        (
            (
                "https://boards.greenhouse.io/"
                "another-company/jobs/98765"
                "?source=linkedin"
            ),
            GreenhouseReference(
                board_token="another-company",
                job_id="98765",
            ),
        ),
        (
            "https://job-boards.greenhouse.io/example",
            None,
        ),
        (
            (
                "https://job-boards.greenhouse.io/"
                "example/jobs/not-a-number"
            ),
            None,
        ),
        (
            "https://jobs.lever.co/example/12345",
            None,
        ),
    ],
)
def test_parse_greenhouse_url(
    url: str,
    expected_reference: GreenhouseReference | None,
) -> None:
    assert parse_greenhouse_url(url) == expected_reference

def test_fetch_greenhouse_job() -> None:
    async def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        assert str(request.url) == (
            "https://boards-api.greenhouse.io/"
            "v1/boards/example/jobs/12345"
        )

        return httpx2.Response(
            status_code=200,
            json={
                "id": 12345,
                "title": "Junior Data Engineer",
                "company_name": "Example Company",
                "location": {
                    "name": "Paris, France"
                },
                "content": (
                    "&lt;p&gt;"
                    "Build reliable data pipelines."
                    "&lt;/p&gt;"
                ),
                "first_published": (
                    "2026-07-01T09:00:00Z"
                ),
                "application_deadline": (
                    "2026-08-15T23:59:00Z"
                ),
                "absolute_url": (
                    "https://job-boards.greenhouse.io/"
                    "example/jobs/12345"
                ),
            },
            request=request,
        )

    async def run_test():
        transport = httpx2.MockTransport(handler)

        async with httpx2.AsyncClient(
            transport=transport,
        ) as client:
            return await fetch_greenhouse_job(
                reference=GreenhouseReference(
                    board_token="example",
                    job_id="12345",
                ),
                source_url=(
                    "https://job-boards.greenhouse.io/"
                    "example/jobs/12345"
                ),
                client=client,
            )

    job = asyncio.run(run_test())

    assert job.title == "Junior Data Engineer"
    assert job.company == "Example Company"
    assert job.location == "Paris, France"
    assert job.description == (
        "Build reliable data pipelines."
    )
    assert job.date_posted == (
        "2026-07-01T09:00:00Z"
    )
    assert job.valid_through == (
        "2026-08-15T23:59:00Z"
    )
    assert job.employment_types == []

@pytest.mark.parametrize(
    ("url", "expected_reference"),
    [
        (
            (
                "https://jobs.lever.co/"
                "example/"
                "f2f01e16-27f8-4711-a728-7d49499795a0"
            ),
            LeverReference(
                site="example",
                posting_id=(
                    "f2f01e16-27f8-4711-a728-7d49499795a0"
                ),
                api_host="api.lever.co",
            ),
        ),
        (
            (
                "https://jobs.eu.lever.co/"
                "example/eu-posting-id"
                "?source=linkedin"
            ),
            LeverReference(
                site="example",
                posting_id="eu-posting-id",
                api_host="api.eu.lever.co",
            ),
        ),
        (
            "https://jobs.lever.co/example",
            None,
        ),
        (
            "https://company.example.com/jobs/123",
            None,
        ),
    ],
)
def test_parse_lever_url(
    url: str,
    expected_reference: LeverReference | None,
) -> None:
    assert parse_lever_url(url) == expected_reference

def test_fetch_lever_job() -> None:
    posting_id = (
        "f2f01e16-27f8-4711-a728-7d49499795a0"
    )

    async def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        assert str(request.url) == (
            "https://api.lever.co/v0/postings/"
            f"example/{posting_id}"
        )

        return httpx2.Response(
            status_code=200,
            json={
                "id": posting_id,
                "text": "Machine Learning Engineer",
                "categories": {
                    "location": "Rennes",
                    "commitment": "Full-time",
                    "team": "Engineering",
                },
                "country": "FR",
                "descriptionPlain": (
                    "Develop and deploy "
                    "machine-learning systems."
                ),
                "hostedUrl": (
                    "https://jobs.lever.co/"
                    f"example/{posting_id}"
                ),
                "applyUrl": (
                    "https://jobs.lever.co/"
                    f"example/{posting_id}/apply"
                ),
            },
            request=request,
        )

    async def run_test():
        transport = httpx2.MockTransport(handler)

        async with httpx2.AsyncClient(
            transport=transport,
        ) as client:
            return await fetch_lever_job(
                reference=LeverReference(
                    site="example",
                    posting_id=posting_id,
                    api_host="api.lever.co",
                ),
                source_url=(
                    "https://jobs.lever.co/"
                    f"example/{posting_id}"
                ),
                client=client,
            )

    job = asyncio.run(run_test())

    assert job.title == (
        "Machine Learning Engineer"
    )
    assert job.company is None
    assert job.location == "Rennes, FR"
    assert job.description == (
        "Develop and deploy "
        "machine-learning systems."
    )
    assert job.employment_types == [
        "Full-time"
    ]
    assert job.application_url == (
        "https://jobs.lever.co/"
        f"example/{posting_id}/apply"
    )

def test_extract_ats_job_dispatcher() -> None:
    async def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        return httpx2.Response(
            status_code=200,
            json={
                "id": 12345,
                "title": "Junior Data Engineer",
                "company_name": "Example Company",
                "location": {
                    "name": "Paris, France"
                },
                "content": (
                    "<p>Build reliable data pipelines.</p>"
                ),
                "absolute_url": (
                    "https://job-boards.greenhouse.io/"
                    "example/jobs/12345"
                ),
            },
            request=request,
        )

    async def run_test():
        transport = httpx2.MockTransport(handler)

        async with httpx2.AsyncClient(
            transport=transport,
        ) as client:
            greenhouse_result = await extract_ats_job(
                (
                    "https://job-boards.greenhouse.io/"
                    "example/jobs/12345"
                ),
                client=client,
            )

            generic_result = await extract_ats_job(
                (
                    "https://company.example.com/"
                    "careers/data-engineer"
                ),
                client=client,
            )

            return greenhouse_result, generic_result

    greenhouse_result, generic_result = asyncio.run(
        run_test()
    )

    assert greenhouse_result is not None
    assert (
        greenhouse_result.extraction_method
        == JobSource.GREENHOUSE
    )
    assert (
        greenhouse_result.job.title
        == "Junior Data Engineer"
    )

    assert generic_result is None

def test_extract_generic_job_content() -> None:
    html = """
    <html>
      <head>
        <title>
          Junior Data Engineer | Example Company
        </title>
        <style>
          body { font-family: sans-serif; }
        </style>
      </head>
      <body>
        <nav>
          Home Careers About Contact
        </nav>

        <main>
          <article>
            <h1>Junior Data Engineer</h1>

            <p>
              Example Company is looking for a Junior Data
              Engineer to build and maintain reliable data
              pipelines for analytics and machine-learning
              applications.
            </p>

            <h2>Responsibilities</h2>

            <p>
              Develop Python and SQL pipelines, validate data
              quality, improve processing reliability, and
              collaborate with analytics and engineering teams.
            </p>

            <h2>Requirements</h2>

            <p>
              Experience with Python, SQL, APIs, relational
              databases, automated testing, and basic cloud
              or container technologies is preferred.
            </p>
          </article>
        </main>

        <footer>
          Privacy policy and cookie settings
        </footer>

        <script>
          console.log("tracking");
        </script>
      </body>
    </html>
    """

    result = extract_generic_job_content(
        html=html,
        source_url=(
            "https://company.example.com/"
            "careers/junior-data-engineer"
        ),
    )

    assert result.page_title == "Junior Data Engineer"
    assert result.source_url == (
        "https://company.example.com/"
        "careers/junior-data-engineer"
    )
    assert "Junior Data Engineer" in result.text
    assert "Develop Python and SQL pipelines" in result.text
    assert "console.log" not in result.text
    assert len(result.text) >= 200

def test_generic_content_rejects_short_page() -> None:
    html = """
    <html>
      <body>
        <p>Enable JavaScript to continue.</p>
      </body>
    </html>
    """

    with pytest.raises(
        GenericContentExtractionError,
        match="useful job information",
    ):
        extract_generic_job_content(
            html=html,
            source_url="https://company.example.com/jobs/123",
        )

def test_ollama_job_extraction_client() -> None:
    class FakeOllamaClient:
        def __init__(self) -> None:
            self.received_model: str | None = None
            self.received_messages: list[dict] | None = None
            self.received_format: dict | None = None

        async def chat(
            self,
            *,
            model,
            messages,
            format,
            options,
            think,
            stream,
            keep_alive,
        ):
            self.received_model = model
            self.received_messages = messages
            self.received_format = format

            return SimpleNamespace(
                message=SimpleNamespace(
                    content="""
                    {
                      "title": "Junior Data Engineer",
                      "company": "Example Company",
                      "location": "Paris, France",
                      "description": "Build reliable data pipelines.",
                      "employment_types": ["FULL_TIME"],
                      "date_posted": null,
                      "valid_through": null,
                      "application_url": "https://invented.example.com"
                    }
                    """
                )
            )

    async def run_test():
        fake_client = FakeOllamaClient()

        settings = Settings(
            ollama_host="http://localhost:11434",
            ollama_model="test-model",
            ollama_timeout_seconds=10,
        )

        extraction_client = OllamaJobExtractionClient(
            settings=settings,
            client=fake_client,
        )

        content = GenericJobContent(
            page_title=(
                "Junior Data Engineer | Example Company"
            ),
            text=(
                "Example Company is looking for a Junior Data "
                "Engineer to build reliable Python and SQL data "
                "pipelines. The candidate will validate data "
                "quality, maintain APIs, write automated tests, "
                "and collaborate with engineering teams. This "
                "is a full-time role based in Paris, France."
            ),
            source_url=(
                "https://company.example.com/"
                "careers/junior-data-engineer"
            ),
        )

        job = await extraction_client.extract_job(content)

        return job, fake_client

    job, fake_client = asyncio.run(run_test())

    assert job.title == "Junior Data Engineer"
    assert job.company == "Example Company"
    assert job.location == "Paris, France"
    assert job.employment_types == ["FULL_TIME"]

    # ApplyFlow must use the trusted source URL, not the
    # URL returned by the model.
    assert job.application_url == (
        "https://company.example.com/"
        "careers/junior-data-engineer"
    )

    assert fake_client.received_model == "test-model"
    assert fake_client.received_messages is not None
    assert fake_client.received_format is not None
