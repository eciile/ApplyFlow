"""Deterministic job-to-candidate matching utilities."""

import re
from collections.abc import Iterable
import unicodedata
from dataclasses import dataclass

from geopy.distance import geodesic

SKILL_ALIASES: dict[str, str] = {
    "python 3": "python",
    "postgres": "postgresql",
    "postgres sql": "postgresql",
    "rest apis": "rest api",
    "restful api": "rest api",
    "restful apis": "rest api",
    "ml": "machine learning",
    "nlp": "natural language processing",
}


def normalize_skill(skill: str) -> str:
    """
    Normalize a skill name for deterministic comparison.

    The displayed skill value is not changed. This normalized
    value is used only internally when comparing skills.
    """

    normalized = skill.casefold().strip()

    normalized = re.sub(
        r"[-_/]+",
        " ",
        normalized,
    )

    # Keep characters used by technologies such as C++, C#,
    # and .NET.
    normalized = re.sub(
        r"[^\w\s+#.]",
        "",
        normalized,
    )

    normalized = " ".join(normalized.split())

    return SKILL_ALIASES.get(
        normalized,
        normalized,
    )


def match_skills(
    candidate_skills: Iterable[str],
    job_skills: Iterable[str],
) -> tuple[list[str], list[str]]:
    """
    Separate job skills into matching and missing lists.

    Returned values preserve the wording used by the job.
    """

    normalized_candidate_skills = {
        normalize_skill(skill)
        for skill in candidate_skills
        if skill.strip()
    }

    matching: list[str] = []
    missing: list[str] = []
    seen_job_skills: set[str] = set()

    for job_skill in job_skills:
        if not job_skill.strip():
            continue

        normalized_job_skill = normalize_skill(job_skill)

        if not normalized_job_skill:
            continue

        if normalized_job_skill in seen_job_skills:
            continue

        seen_job_skills.add(normalized_job_skill)

        if normalized_job_skill in normalized_candidate_skills:
            matching.append(job_skill)
        else:
            missing.append(job_skill)

    return matching, missing

REQUIRED_SKILLS_WEIGHT = 60.0
PREFERRED_SKILLS_WEIGHT = 20.0
LOCATION_WEIGHT = 10.0
EMPLOYMENT_TYPE_WEIGHT = 10.0


EMPLOYMENT_TYPE_ALIASES: dict[str, str] = {
    "cdi": "permanent",
    "permanent": "permanent",
    "cdd": "fixed_term",
    "fixed term": "fixed_term",
    "fixed_term": "fixed_term",
    "full time": "full_time",
    "full_time": "full_time",
    "temps plein": "full_time",
    "internship": "internship",
    "stage": "internship",
    "apprenticeship": "apprenticeship",
    "alternance": "apprenticeship",
}


REMOTE_MARKERS = {
    "remote",
    "teletravail",
    "a distance",
}


@dataclass(frozen=True)
class JobMatchResult:
    """Deterministic and explainable job match result."""

    score: int
    recommendation: str

    matching_required_skills: list[str]
    missing_required_skills: list[str]

    matching_preferred_skills: list[str]
    missing_preferred_skills: list[str]

    location_match: bool | None
    location_distance_km: float | None
    maximum_commute_distance_km: float
    location_match_method: str
    employment_type_match: bool | None

    breakdown: dict[str, dict[str, float | bool]]


@dataclass(frozen=True)
class LocationMatchResult:
    """Explain how two locations were compared."""

    matches: bool | None
    distance_km: float | None
    method: str

def normalize_text(value: str) -> str:
    """Normalize ordinary text for preference comparisons."""

    decomposed = unicodedata.normalize(
        "NFKD",
        value.casefold(),
    )

    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )

    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        without_accents,
    )

    return " ".join(normalized.split())


def _location_text_variants(value: str) -> list[str]:
    """Return full and locality-only normalized location labels."""

    variants = [normalize_text(value)]
    if "," in value:
        variants.append(
            normalize_text(value.split(",", 1)[0])
        )

    return list(dict.fromkeys(filter(None, variants)))

def match_location(
    *,
    profile_coordinates: tuple[float, float] | None,
    job_coordinates: tuple[float, float] | None,
    maximum_distance_km: float,
    profile_location: str | None,
    job_location: str | None,
    preferred_locations: Iterable[str],
) -> LocationMatchResult:
    """
    Prefer remote compatibility, then coordinates, then text.
    """

    preferences = [
        variant
        for location in preferred_locations
        if location.strip()
        for variant in _location_text_variants(location)
    ]

    normalized_profile_location = (
        normalize_text(profile_location)
        if profile_location
        else ""
    )
    normalized_job_location = (
        normalize_text(job_location)
        if job_location
        else ""
    )

    candidate_accepts_remote = any(
        preference in REMOTE_MARKERS
        for preference in preferences
    ) or any(
        marker in normalized_profile_location
        for marker in REMOTE_MARKERS
    )
    job_is_remote = any(
        marker in normalized_job_location
        for marker in REMOTE_MARKERS
    )

    if candidate_accepts_remote and job_is_remote:
        return LocationMatchResult(True, None, "remote")

    if (
        profile_coordinates is not None
        and job_coordinates is not None
    ):
        try:
            distance_km = geodesic(
                profile_coordinates,
                job_coordinates,
            ).kilometers
        except ValueError:
            pass
        else:
            return LocationMatchResult(
                distance_km <= maximum_distance_km,
                round(distance_km, 1),
                "distance",
            )

    physical_preferences = [
        preference
        for preference in preferences
        if preference not in REMOTE_MARKERS
    ]
    if normalized_profile_location:
        physical_preferences.extend(
            _location_text_variants(profile_location or "")
        )

    if not normalized_job_location or not physical_preferences:
        return LocationMatchResult(None, None, "unavailable")

    job_with_boundaries = (
        f" {normalized_job_location} "
    )

    for preference in physical_preferences:
        if not preference:
            continue

        preference_with_boundaries = (
            f" {preference} "
        )

        if preference_with_boundaries in job_with_boundaries:
            return LocationMatchResult(True, None, "text")

        if (
            job_with_boundaries
            in preference_with_boundaries
        ):
            return LocationMatchResult(True, None, "text")

    return LocationMatchResult(False, None, "text")
def normalize_employment_type(
    employment_type: str,
) -> str:
    """Normalize employment-type labels."""

    normalized = normalize_text(
        employment_type
    )

    return EMPLOYMENT_TYPE_ALIASES.get(
        normalized,
        normalized,
    )


def match_employment_type(
    job_employment_types: Iterable[str],
    preferred_employment_types: Iterable[str],
) -> bool | None:
    """
    Compare job contract types with candidate preferences.

    None means there was not enough information to compare.
    """

    job_types = {
        normalize_employment_type(value)
        for value in job_employment_types
        if value.strip()
    }

    preferred_types = {
        normalize_employment_type(value)
        for value in preferred_employment_types
        if value.strip()
    }

    if not job_types or not preferred_types:
        return None

    return bool(
        job_types.intersection(preferred_types)
    )

def calculate_job_match(
    *,
    candidate_skills: Iterable[str],
    required_skills: Iterable[str],
    preferred_skills: Iterable[str],
    job_location: str | None,
    preferred_locations: Iterable[str],
    profile_location: str | None = None,
    profile_coordinates: tuple[float, float] | None = None,
    job_coordinates: tuple[float, float] | None = None,
    maximum_commute_distance_km: float = 30,
    job_employment_types: Iterable[str],
    preferred_employment_types: Iterable[str],
) -> JobMatchResult:
    """Calculate a deterministic job match."""

    candidate_skill_list = list(candidate_skills)
    required_skill_list = list(required_skills)
    preferred_skill_list = list(preferred_skills)
    preferred_location_list = list(
        preferred_locations
    )
    job_employment_type_list = list(
        job_employment_types
    )
    preferred_employment_type_list = list(
        preferred_employment_types
    )

    (
        matching_required,
        missing_required,
    ) = match_skills(
        candidate_skill_list,
        required_skill_list,
    )

    (
        matching_preferred,
        missing_preferred,
    ) = match_skills(
        candidate_skill_list,
        preferred_skill_list,
    )

    required_total = (
        len(matching_required)
        + len(missing_required)
    )
    preferred_total = (
        len(matching_preferred)
        + len(missing_preferred)
    )

    required_ratio = (
        len(matching_required) / required_total
        if required_total
        else 0.0
    )

    preferred_ratio = (
        len(matching_preferred) / preferred_total
        if preferred_total
        else 0.0
    )

    location_result = match_location(
        profile_coordinates=profile_coordinates,
        job_coordinates=job_coordinates,
        maximum_distance_km=maximum_commute_distance_km,
        profile_location=profile_location,
        job_location=job_location,
        preferred_locations=preferred_location_list,
    )
    location_match = location_result.matches

    employment_type_match = (
        match_employment_type(
            job_employment_type_list,
            preferred_employment_type_list,
        )
    )

    category_data = {
        "required_skills": {
            "weight": REQUIRED_SKILLS_WEIGHT,
            "ratio": required_ratio,
            "available": required_total > 0,
        },
        "preferred_skills": {
            "weight": PREFERRED_SKILLS_WEIGHT,
            "ratio": preferred_ratio,
            "available": preferred_total > 0,
        },
        "location": {
            "weight": LOCATION_WEIGHT,
            "ratio": (
                1.0
                if location_match is True
                else 0.0
            ),
            "available": location_match is not None,
        },
        "employment_type": {
            "weight": EMPLOYMENT_TYPE_WEIGHT,
            "ratio": (
                1.0
                if employment_type_match is True
                else 0.0
            ),
            "available": (
                employment_type_match is not None
            ),
        },
    }

    available_weight = sum(
        category["weight"]
        for category in category_data.values()
        if category["available"]
    )

    breakdown: dict[
        str,
        dict[str, float | bool],
    ] = {}

    total_score = 0.0

    for category_name, category in (
        category_data.items()
    ):
        available = bool(category["available"])

        if available and available_weight:
            adjusted_maximum = (
                float(category["weight"])
                / available_weight
                * 100
            )

            category_score = (
                float(category["ratio"])
                * adjusted_maximum
            )
        else:
            adjusted_maximum = 0.0
            category_score = 0.0

        total_score += category_score

        breakdown[category_name] = {
            "score": round(category_score, 2),
            "maximum": round(
                adjusted_maximum,
                2,
            ),
            "available": available,
        }

    final_score = round(total_score)

    recommendation = _recommendation_for_score(
        final_score
    )

    if (
        recommendation == "strong_match"
        and required_total > 0
        and len(missing_required)
        > required_total / 2
    ):
        recommendation = "good_match"

    return JobMatchResult(
        score=final_score,
        recommendation=recommendation,
        matching_required_skills=(
            matching_required
        ),
        missing_required_skills=(
            missing_required
        ),
        matching_preferred_skills=(
            matching_preferred
        ),
        missing_preferred_skills=(
            missing_preferred
        ),
        location_match=location_match,
        location_distance_km=location_result.distance_km,
        maximum_commute_distance_km=(
            maximum_commute_distance_km
        ),
        location_match_method=location_result.method,
        employment_type_match=(
            employment_type_match
        ),
        breakdown=breakdown,
    )

def _recommendation_for_score(
    score: int,
) -> str:
    """Convert a numeric score into a recommendation."""

    if score >= 80:
        return "strong_match"

    if score >= 60:
        return "good_match"

    if score >= 40:
        return "partial_match"

    return "weak_match"
