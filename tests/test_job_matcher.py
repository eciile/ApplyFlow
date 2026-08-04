from app.services.job_matcher import match_location


def test_location_matches_within_commute_radius() -> None:
    result = match_location(
        profile_coordinates=(48.1212, -1.6030),
        job_coordinates=(48.1173, -1.6778),
        maximum_distance_km=30,
        profile_location="Cesson-Sévigné, France",
        job_location="Rennes, France",
        preferred_locations=[],
    )

    assert result.matches is True
    assert result.distance_km is not None
    assert result.distance_km < 10
    assert result.method == "distance"


def test_location_outside_commute_radius_does_not_match() -> None:
    result = match_location(
        profile_coordinates=(48.1212, -1.6030),
        job_coordinates=(48.8566, 2.3522),
        maximum_distance_km=30,
        profile_location="Cesson-Sévigné, France",
        job_location="Paris, France",
        preferred_locations=[],
    )

    assert result.matches is False
    assert result.distance_km is not None
    assert result.distance_km > 300
    assert result.method == "distance"


def test_remote_compatibility_takes_precedence_over_distance() -> None:
    result = match_location(
        profile_coordinates=(48.1212, -1.6030),
        job_coordinates=(48.8566, 2.3522),
        maximum_distance_km=30,
        profile_location="Cesson-Sévigné, France",
        job_location="Paris — Télétravail",
        preferred_locations=["Remote"],
    )

    assert result.matches is True
    assert result.distance_km is None
    assert result.method == "remote"


def test_location_falls_back_to_normalized_text() -> None:
    result = match_location(
        profile_coordinates=None,
        job_coordinates=None,
        maximum_distance_km=30,
        profile_location="Rennes, France",
        job_location="Rennes (35)",
        preferred_locations=[],
    )

    assert result.matches is True
    assert result.distance_km is None
    assert result.method == "text"


def test_unusable_location_is_unknown() -> None:
    result = match_location(
        profile_coordinates=None,
        job_coordinates=None,
        maximum_distance_km=30,
        profile_location=None,
        job_location="Rennes, France",
        preferred_locations=[],
    )

    assert result.matches is None
    assert result.distance_km is None
    assert result.method == "unavailable"
