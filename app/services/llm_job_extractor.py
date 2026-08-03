from __future__ import annotations
import json
import httpx
from ollama import AsyncClient, ResponseError
from pydantic import ValidationError
from app.config import Settings, get_settings
from app.schemas import ExtractedJobPosting, GenericJobContent
from functools import lru_cache

MAX_INPUT_CHARACTERS = 4_000
SYSTEM_PROMPT = """
You extract structured information from job advertisements.

Rules:
- Use only information explicitly present in the provided content.
- Never invent company names, locations, dates, or employment types.
- Extract employment type whenever terms such as full-time,
  part-time, permanent, temporary, contract, internship,
  apprenticeship, freelance, or fixed-term are explicitly stated.
- Preserve the wording used in the source text.
- Return null for unavailable optional values.
- Return an empty list when employment type is unavailable.
- Keep the description concise but faithful to the source.
- Return only data matching the requested JSON schema.
""".strip()


class LlmJobExtractionError(ValueError):
    """raised when the LLM fails to produce a valid job posting"""

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
                    "num_predict": 256,
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
                "ApplyFlow could not connect to the Ollama server."
            ) from exc

        except httpx.HTTPError as exc:
            raise LlmJobExtractionError(
                f"Ollama request failed: {type(exc).__name__}."
            ) from exc

        except ConnectionError as exc:
            raise LlmJobExtractionError(
                "ApplyFlow could not connect to the Ollama server."
            ) from exc

        raw_content = response.message.content

        if not raw_content or not raw_content.strip():
            raise LlmJobExtractionError(
                "Ollama returned an empty response."
            )

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

        # The source URL is controlled by ApplyFlow. Do not trust the
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
