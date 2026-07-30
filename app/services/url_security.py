from __future__ import annotations

import asyncio
import socket
from ipaddress import ip_address
from urllib.parse import urlsplit


ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
}

BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home.arpa",
)


class UnsafeUrlError(ValueError):
    """Raised when a URL could target a local or unsafe resource."""


async def resolve_hostname(
    hostname: str,
    port: int,
) -> set[str]:
    """Resolve every IPv4 and IPv6 address associated with a hostname."""

    try:
        results = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeUrlError(
            "The URL hostname could not be resolved."
        ) from exc

    addresses = {
        result[4][0]
        for result in results
        if result[4]
    }

    if not addresses:
        raise UnsafeUrlError(
            "The URL hostname did not resolve to an IP address."
        )

    return addresses


def ensure_global_ip(address_value: str) -> None:
    """Reject IP addresses that are not globally reachable."""

    # IPv6 addresses may contain a scope identifier such as "%eth0".
    normalized_address = address_value.split("%", maxsplit=1)[0]

    try:
        address = ip_address(normalized_address)
    except ValueError as exc:
        raise UnsafeUrlError(
            "The hostname resolved to an invalid IP address."
        ) from exc

    if not address.is_global:
        raise UnsafeUrlError(
            "The URL resolves to a non-public IP address."
        )


async def ensure_public_url(url: str) -> None:
    """
    Ensure a URL points to a public HTTP or HTTPS destination.

    This validation must be repeated for every redirect.
    """

    parsed = urlsplit(url)

    scheme = parsed.scheme.lower()

    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(
            "Only HTTP and HTTPS URLs are allowed."
        )

    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError(
            "URLs containing credentials are not allowed."
        )

    hostname = parsed.hostname

    if not hostname:
        raise UnsafeUrlError(
            "The URL must include a hostname."
        )

    normalized_hostname = hostname.lower().rstrip(".")

    if (
        normalized_hostname in BLOCKED_HOSTNAMES
        or normalized_hostname.endswith(BLOCKED_SUFFIXES)
    ):
        raise UnsafeUrlError(
            "Local hostnames are not allowed."
        )

    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError(
            "The URL contains an invalid port."
        ) from exc

    effective_port = port or (443 if scheme == "https" else 80)

    if effective_port not in ALLOWED_PORTS:
        raise UnsafeUrlError(
            "Only ports 80 and 443 are allowed."
        )

    # Handle direct IP-address URLs without DNS resolution.
    try:
        direct_address = ip_address(normalized_hostname)
    except ValueError:
        direct_address = None

    if direct_address is not None:
        ensure_global_ip(str(direct_address))
        return

    addresses = await resolve_hostname(
        normalized_hostname,
        effective_port,
    )

    for address_value in addresses:
        ensure_global_ip(address_value)