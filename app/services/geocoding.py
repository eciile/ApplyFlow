"""Client for the official French Géoplateforme geocoder."""

from __future__ import annotations

import logging
from typing import Any

import httpx

GEOCODING_URL = "https://data.geopf.fr/geocodage/search"
GEOCODING_TIMEOUT_SECONDS = 5.0
logger = logging.getLogger(__name__)


def geocode_location(
    location: str,
) -> tuple[float, float] | None:
    """Return a municipality's latitude/longitude, if found."""

    query = " ".join(location.split())
    if not query:
        return None

    try:
        response = httpx.get(
            GEOCODING_URL,
            params={
                "q": query,
                "limit": 1,
                "type": "municipality",
            },
            headers={
                "User-Agent": "JobMatch/0.2",
                "Accept": "application/json",
            },
            timeout=GEOCODING_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload: Any = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "Could not geocode location %r: %s",
            query,
            exc,
        )
        return None

    try:
        longitude, latitude = payload["features"][0]["geometry"]["coordinates"]
        latitude = float(latitude)
        longitude = float(longitude)
    except (KeyError, IndexError, TypeError, ValueError):
        return None

    if not (-90 <= latitude <= 90):
        return None
    if not (-180 <= longitude <= 180):
        return None

    return latitude, longitude
