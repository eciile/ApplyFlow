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