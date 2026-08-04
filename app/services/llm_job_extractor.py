from __future__ import annotations
import json
import httpx
from ollama import AsyncClient, ResponseError
from pydantic import BaseModel, Field, ValidationError
from typing import Literal
from app.config import Settings, get_settings
from app.schemas import (
    ExtractedJobPosting,
    GenericJobContent,
    JobRequirements,
)
from app.text_utils import repair_utf8_mojibake
from functools import lru_cache

MAX_INPUT_CHARACTERS = 4_000
REQUIREMENTS_SECTION_START_MARKERS = (
    "minimum qualifications",
    "required qualifications",
    "basic qualifications",
    "what we're looking for",
    "what we are looking for",
    "what you bring",
    "what you'll bring",
    "what you will bring",
    "it would be great if you have",
    "skills and experience",
    "your qualifications",
    "your profile",
    "about you",
    "who you are",
    "requirements",
)
REQUIREMENTS_SECTION_END_MARKERS = (
    "what's in it for you",
    "what’s in it for you",
    "what we offer",
    "our benefits",
    "benefits and perks",
    "next steps",
    "interview process",
    "about the company",
    "about us",
    "equal opportunity",
)
OPTIONAL_REQUIREMENTS_MARKERS = (
    "nice to have",
    "good to have",
    "preferred qualifications",
    "preferred skills",
    "bonus points",
    "as a bonus",
)
SYSTEM_PROMPT = """
You extract structured information from job advertisements.

Rules:
- Use only information explicitly present in the provided content.
- Never invent company names, locations, dates, or employment types.
- Extract employment type whenever terms such as full-time,
  part-time, permanent, temporary, contract, internship,
  apprenticeship, freelance, or fixed-term are explicitly stated.
- Put mandatory technical skills, tools, frameworks, platforms,
  and methodologies under required_skills.
- Put optional, desirable, preferred, or bonus technical skills
  under preferred_skills.
- Put degrees, certifications, licences, years of experience,
  and other formal eligibility criteria under qualifications.
- Put explicitly requested interpersonal or behavioural abilities
  such as communication, teamwork, autonomy, and leadership under
  soft_skills.
- Put explicitly requested spoken or written languages under
  languages.
- Do not classify programming languages such as Python,
  Java, or SQL as spoken languages.
- Do not infer requirements that are not explicitly stated.
- Include soft skills only when the advertisement presents them
  as an explicit requirement.
- Candidate evidence rule: include an item only when the advertisement
  directly asks the candidate to have it. Typical evidence appears under
  headings such as requirements, qualifications, what you bring, you have,
  your profile, or nice to have.
- Technologies mentioned only in company or team descriptions, existing
  stack lists, product architecture, responsibilities, examples, benefits,
  interview steps, or employer boilerplate are context, not requirements.
- A responsibility involving a technology does not by itself prove that
  prior skill in that technology is required.
- Never turn a responsibility into an inferred soft skill. For example,
  "collaborate with other teams" does not imply "collaboration" belongs
  under soft_skills unless collaboration is explicitly requested as a trait.
- Required skills include wording such as:
  required, must have, essential, indispensable,
  maîtrise requise, obligatoire, or prerequisites.
- Preferred skills include wording such as:
  preferred, desirable, bonus, nice to have,
  apprécié, souhaité, idéalement, or un plus.
- Preserve common technology names such as Python,
  PostgreSQL, FastAPI, Docker, AWS, and Apache Airflow.
- Do not place the same skill in both required_skills
  and preferred_skills.
- Preserve the wording used in the source text.
- required_skills and preferred_skills must contain only
  short, atomic skill or technology names.
- Never return full sentences, qualification statements,
  responsibilities, degrees, or experience descriptions
  inside skill lists.
- Split combined requirements into separate items.
- For example, "Java or Python development using APIs and
  microservices" becomes ["Java", "Python", "REST API",
  "Microservices"]. and "Maîtrise de Java ou Python, des API et des microservices"
  becomes ["Java", "Python", "REST API", "Microservices"].
- Keep each skill concise, normally between one and five words.
- Degrees, certifications, and years of experience belong under
  qualifications, never under skill lists.
- Do not place the same item in multiple requirement categories.
- Do not put the same skill in both required_skills and
  preferred_skills.
- Return null for unavailable optional values.
- Return an empty list when employment type is unavailable.
- Keep the description concise but faithful to the source.
- Return only data matching the requested JSON schema.
""".strip()


class LlmJobExtractionError(ValueError):
    """raised when the LLM fails to produce a valid job posting"""


class CategorizedRequirement(BaseModel):
    """One atomic requirement classified by its public output field."""

    value: str = Field(min_length=1)
    category: Literal[
        "required_skills",
        "preferred_skills",
        "qualifications",
        "soft_skills",
        "languages",
    ]


class CategorizedRequirements(BaseModel):
    """Internal LLM response that avoids parallel defaulted arrays."""

    items: list[CategorizedRequirement]

class OllamaJobExtractionClient:
    """extract structured job data using a local Ollama model"""
    def __init__(
            self,
            settings:Settings|None=None,
            client:AsyncClient|None=None
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or AsyncClient(
            host=self.settings.ollama_host,
            timeout=self.settings.ollama_timeout_seconds,
        )
    async def extract_job(
        self,
        content: GenericJobContent,
    ) -> ExtractedJobPosting:
        """Convert cleaned page content into structured job data."""

        schema = ExtractedJobPosting.model_json_schema()

        prompt = _build_prompt(content)

        try:
            response = await self.client.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                format=schema,
                options={
                    "temperature": 0,
                    "num_ctx": 4096,
                    "num_predict": 512,
                },
                think=False,
                stream=False,
                keep_alive="10m",
            )

        except ResponseError as exc:
            raise LlmJobExtractionError(
                f"Ollama returned an error: {exc.error}"
            ) from exc

        except httpx.TimeoutException as exc:
            raise LlmJobExtractionError(
                "Ollama did not finish extraction before the timeout."
            ) from exc

        except httpx.ConnectError as exc:
            raise LlmJobExtractionError(
                "JobMatch could not connect to the Ollama server."
            ) from exc

        except httpx.HTTPError as exc:
            raise LlmJobExtractionError(
                f"Ollama request failed: {type(exc).__name__}."
            ) from exc

        except ConnectionError as exc:
            raise LlmJobExtractionError(
                "JobMatch could not connect to the Ollama server."
            ) from exc

        raw_content = response.message.content

        if not raw_content or not raw_content.strip():
            raise LlmJobExtractionError(
                "Ollama returned an empty response."
            )

        raw_content = repair_utf8_mojibake(raw_content)

        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise LlmJobExtractionError(
                "Ollama returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise LlmJobExtractionError(
                "Ollama returned an unexpected JSON structure."
            )

        # The source URL is controlled by JobMatch. Do not trust the
        # model to generate or reproduce an application URL.
        payload["application_url"] = content.source_url

        try:
            job = ExtractedJobPosting.model_validate(payload)
        except ValidationError as exc:
            raise LlmJobExtractionError(
                "Ollama returned job data that failed validation."
            ) from exc

        generic_title_markers = {
            "détails offre",
            "detail offre",
            "job details",
            "offre d'emploi",
            "careers",
            "carrières",
            "recrutement",
        }

        normalized_title = job.title.casefold()

        if any(
            marker in normalized_title
            for marker in generic_title_markers
        ):
            raise LlmJobExtractionError(
                "Ollama did not extract a specific job title."
            )

        if not job.description:
            job = job.model_copy(
                update={
                    "description": _build_description_fallback(
                        content.text
                    )
                }
            )
        return job

    async def extract_requirements(
        self,
        *,
        title: str,
        description: str,
    ) -> JobRequirements:
        """Extract atomic requirements from an existing job."""

        requirements_text = _select_requirements_text(description)
        requirements_text = _label_requirement_priority(
            requirements_text
        )

        prompt = f"""
        Return every explicit candidate criterion as an atomic categorized
        item.

        Job title:
        {title}

        Candidate criteria:
        --- BEGIN CRITERIA ---
        {requirements_text[:MAX_INPUT_CHARACTERS]}
        --- END CRITERIA ---

        Categories:
        - required_skills: named technologies and practical technical
          abilities in MAIN CANDIDATE CRITERIA.
        - preferred_skills: named technologies and practical technical
          abilities in OPTIONAL / NICE-TO-HAVE CRITERIA.
        - qualifications: experience, durations, degrees, certifications,
          licences, academic or professional background, and theoretical
          knowledge. These are qualifications even when technically themed.
        - soft_skills: explicit behavioural or interpersonal traits.
        - languages: explicit human-language requirements only.

        Classification examples:
        - "multiple years of Python experience" yields two items: Python as
          required_skills and the full experience criterion as qualifications.
        - "strong computer science background" is qualifications.
        - "LLM and AI Engineering theoretical knowledge" yields three items:
          LLM Engineering and AI Engineering as required_skills, plus the
          knowledge criterion as qualifications.
        - "good communication skills" is soft_skills.
        - "PyTorch experience" in the OPTIONAL section yields PyTorch as
          preferred_skills.

        For every qualification with a named technical subject, also emit
        that subject as an atomic technical skill. Use required_skills for a
        MAIN criterion and preferred_skills for an OPTIONAL criterion.
        Keep the qualification item even when its technical subject was also
        emitted as a skill.

        Expand shared suffixes into complete atomic names. For example,
        "LLM / AI Engineering" must produce "LLM Engineering" and
        "AI Engineering", never the incomplete value "LLM".

        Normalize qualification wording without changing its meaning:
        - "first experience in X" becomes "X experience".
        - "at least N years of experience programming in X" becomes
          "N+ years X experience".
        - Remove evaluative modifiers such as "good" or "strong" from
          background and theoretical-knowledge qualifications.

        Account for every explicit criterion. Preserve exact numbers and do
        not copy durations from examples. Split alternatives and named
        technologies into atomic items. Do not output both a short and long
        version of the same criterion within one category. Do not infer
        missing criteria.
        """.strip()

        try:
            response = await self.client.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Classify explicit candidate criteria into the "
                            "requested JSON fields without omissions."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                format=CategorizedRequirements.model_json_schema(),
                options={
                    "temperature": 0,
                    "num_ctx": 4096,
                    "num_predict": 512,
                },
                think=False,
                stream=False,
                keep_alive="10m",
            )
        except ResponseError as exc:
            raise LlmJobExtractionError(
                f"Ollama returned an error: {exc.error}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LlmJobExtractionError(
                "Ollama did not finish requirements extraction "
                "before the timeout."
            ) from exc
        except httpx.ConnectError as exc:
            raise LlmJobExtractionError(
                "JobMatch could not connect to the Ollama server."
            ) from exc
        except httpx.HTTPError as exc:
            raise LlmJobExtractionError(
                f"Ollama request failed: {type(exc).__name__}."
            ) from exc
        except ConnectionError as exc:
            raise LlmJobExtractionError(
                "JobMatch could not connect to the Ollama server."
            ) from exc

        raw_content = response.message.content

        if not raw_content or not raw_content.strip():
            raise LlmJobExtractionError(
                "Ollama returned empty job requirements."
            )

        raw_content = repair_utf8_mojibake(raw_content)

        try:
            payload = json.loads(raw_content)
            categorized = CategorizedRequirements.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LlmJobExtractionError(
                "Ollama returned invalid job requirements."
            ) from exc

        grouped: dict[str, list[str]] = {
            "required_skills": [],
            "preferred_skills": [],
            "qualifications": [],
            "soft_skills": [],
            "languages": [],
        }

        for item in categorized.items:
            grouped[item.category].append(item.value)

        return JobRequirements.model_validate(grouped)


def _select_requirements_text(description: str) -> str:
    """
    Prefer an explicit candidate-requirements section when present.

    ATS descriptions are often flattened into one long string. This keeps
    company stack and benefits sections from being presented to the model as
    candidate requirements while retaining the full text as a fallback.
    """

    normalized = description.casefold()
    start_positions = [
        position
        for marker in REQUIREMENTS_SECTION_START_MARKERS
        if (position := normalized.find(marker)) >= 0
    ]

    if not start_positions:
        return description

    start = min(start_positions)
    end_positions = [
        position
        for marker in REQUIREMENTS_SECTION_END_MARKERS
        if (position := normalized.find(marker, start + 1)) >= 0
    ]
    end = min(end_positions) if end_positions else len(description)

    return description[start:end].strip()


def _label_requirement_priority(text: str) -> str:
    """Label an optional subsection so small models preserve priority."""

    normalized = text.casefold()
    optional_positions = [
        (position, marker)
        for marker in OPTIONAL_REQUIREMENTS_MARKERS
        if (position := normalized.find(marker)) > 0
    ]

    if not optional_positions:
        return text

    position, marker = min(optional_positions)
    main_requirements = text[:position].strip()
    optional_requirements = text[
        position + len(marker):
    ].strip(" :.-")

    return (
        "MAIN CANDIDATE CRITERIA:\n"
        f"{main_requirements}\n\n"
        "OPTIONAL / NICE-TO-HAVE CRITERIA:\n"
        f"{optional_requirements}"
    )

def _build_prompt(
    content: GenericJobContent,
) -> str:
    page_text = content.text[:MAX_INPUT_CHARACTERS]
    page_title = content.page_title or "Unavailable"

    metadata_lines = [
        f"- {key}: {value}"
        for key, value in content.metadata.items()
    ]

    metadata_text = (
        "\n".join(metadata_lines)
        if metadata_lines
        else "- No structured metadata found"
    )

    return f"""
    Extract the job advertisement into structured data.

    Page title:
    {page_title}

    Page metadata:
    {metadata_text}

    Main job content:
    --- BEGIN JOB CONTENT ---
    {page_text}
    --- END JOB CONTENT ---

    Rules:
    - Use only explicitly provided information.
    - The title must not be empty.
    - Empty strings are forbidden.
    - Use null for missing optional string fields.
    - Preserve company and location metadata when supplied.
    - Map CDI to PERMANENT.
    - Map CDD to FIXED_TERM.
    - Map stage to INTERNSHIP.
    - Map alternance to APPRENTICESHIP.
    """.strip()

def _build_description_fallback(
    text: str,
    max_characters: int = 1_500,
) -> str:
    """
    Build a faithful description from cleaned page content.

    This avoids rejecting an otherwise useful extraction when
    the model leaves the description empty.
    """

    cleaned = " ".join(text.split())

    if len(cleaned) <= max_characters:
        return cleaned

    shortened = cleaned[:max_characters]

    # Prefer ending on a complete sentence when possible.
    last_period = shortened.rfind(".")

    if last_period >= max_characters // 2:
        return shortened[: last_period + 1]

    return shortened.rstrip() + "..."

@lru_cache
def get_llm_job_extraction_client() -> OllamaJobExtractionClient:
    """Return one reusable Ollama extraction client."""

    return OllamaJobExtractionClient()
