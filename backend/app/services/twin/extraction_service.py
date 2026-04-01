from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services.ai.openrouter_service import OpenRouterService

logger = logging.getLogger(__name__)
MAX_EXTRACTION_INPUT_CHARS = 5000
LOW_SIGNAL_CONTEXT = "The message does not contain enough cognitive evidence."

SYSTEM_PROMPT = """
You are a strict cognitive extraction engine.

Your job is to convert a single user message into structured behavioral signals.
Extract cognitive tendencies, decision patterns, preferences, and situational context.

Return ONLY valid JSON.
Do not return markdown.
Do not return code fences.
Do not return explanations.
Do not return any text before or after the JSON object.

Target schema:
{
  "thinking_style": "string",
  "decision_traits": ["string"],
  "preferences": ["string"],
  "context": "string"
}

Rules:
1. Focus on behavioral traits, not generic summaries.
2. Only infer traits grounded in the text.
3. If evidence is weak, use "unknown" for thinking_style and keep arrays empty.
4. decision_traits must be short trait phrases, not full sentences.
5. preferences must capture likes, dislikes, or recurring tendencies.
6. context must describe the situation or topic of the message in one short sentence.
7. Never invent biography, profession, age, diagnosis, or deep personality claims.
8. Prefer precise labels like "deliberate", "intuition-led", "evidence-seeking", "novelty-seeking",
   "ambiguity-tolerant", "structure-preferring", "risk-aware", "speed-oriented", "reflection-heavy".
9. Keep decision_traits to at most 5 items.
10. Keep preferences to at most 5 items.

Example 1:
Input: "I usually sleep on major decisions, compare a few options, and only commit when the tradeoffs feel clear. I hate cluttered dashboards."
Output:
{"thinking_style":"reflective and analytical","decision_traits":["deliberate","option-comparing","tradeoff-aware"],"preferences":["clear tradeoffs","low-clutter interfaces"],"context":"The user is describing how they evaluate decisions and consume information."}

Example 2:
Input: "If the direction feels right, I move quickly. I would rather test something in the real world than over-plan it."
Output:
{"thinking_style":"intuitive and action-oriented","decision_traits":["fast-moving","intuition-led","experiment-driven"],"preferences":["real-world testing","low overhead planning"],"context":"The user is describing a bias toward rapid action and live experimentation."}

Example 3:
Input: "okay thanks"
Output:
{"thinking_style":"unknown","decision_traits":[],"preferences":[],"context":"The message does not contain enough cognitive evidence."}
""".strip()


class ExtractionResult(BaseModel):
    thinking_style: str = "unknown"
    decision_traits: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    context: str = "The message does not contain enough cognitive evidence."

    @field_validator("thinking_style", "context", mode="before")
    @classmethod
    def normalize_string(cls, value: Any) -> str:
        if isinstance(value, str):
            normalized = " ".join(value.strip().split())
            return normalized or "unknown"
        return "unknown"

    @field_validator("decision_traits", "preferences", mode="before")
    @classmethod
    def normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = re.split(r"[,;\n]+", value)
        elif isinstance(value, list):
            candidates = [str(item) for item in value]
        else:
            return []

        seen: set[str] = set()
        cleaned: list[str] = []
        for candidate in candidates:
            item = " ".join(candidate.strip().split())
            if not item:
                continue
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            cleaned.append(item)
            if len(cleaned) == 5:
                break
        return cleaned


class ExtractionService:
    def __init__(self, openrouter_service: OpenRouterService | None = None, max_retries: int = 3) -> None:
        self.openrouter_service = openrouter_service or OpenRouterService()
        self.max_retries = max_retries

    def extract_cognition(self, text: str) -> dict[str, Any]:
        cleaned_text = self._prepare_text(text)
        if not cleaned_text:
            logger.info("Received empty text for cognitive extraction.")
            return ExtractionResult().model_dump()

        if self._is_low_signal_text(cleaned_text):
            logger.info("Received low-signal text for cognitive extraction. Returning fallback extraction.")
            return self._fallback_result(cleaned_text)

        if self.openrouter_service.client is None:
            logger.warning("OpenRouter client is not configured. Returning deterministic fallback extraction.")
            return self._fallback_result(cleaned_text)

        last_error: Exception | None = None
        last_raw_response = ""

        for attempt in range(1, self.max_retries + 1):
            logger.info("Cognitive extraction attempt %s/%s", attempt, self.max_retries)
            try:
                raw_response = self._request_extraction(cleaned_text, attempt, last_raw_response, last_error)
                last_raw_response = raw_response
                logger.debug("Raw extraction response: %s", raw_response[:1000])
                parsed = self._parse_response(raw_response)
                return parsed.model_dump()
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                logger.warning("Cognitive extraction parsing failed on attempt %s: %s", attempt, exc)
            except Exception as exc:  # pragma: no cover - depends on network/runtime state
                last_error = exc
                logger.exception("Cognitive extraction model call failed on attempt %s", attempt)

        logger.error("Cognitive extraction failed after %s attempts. Using deterministic fallback.", self.max_retries)
        return self._fallback_result(cleaned_text)

    def _request_extraction(
        self,
        text: str,
        attempt: int,
        previous_raw_response: str,
        previous_error: Exception | None,
    ) -> str:
        if self.openrouter_service.client is None:
            raise RuntimeError("OpenRouter client is not configured.")

        retry_note = ""
        if attempt > 1:
            retry_note = (
                "\n\nThe previous output was invalid JSON or did not follow the schema. "
                f"Error: {previous_error}. Previous output: {previous_raw_response[:600]}"
                "\nReturn a single valid JSON object only. Do not include any prose."
            )

        return self.openrouter_service.call_model_sync(
            task_type="extraction",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Extract structured cognition from the following text.\n"
                        "Return exactly one JSON object matching the schema.\n\n"
                        f"User text: {text}{retry_note}"
                    ),
                },
            ],
        )

    def _parse_response(self, raw_response: str) -> ExtractionResult:
        cleaned = raw_response.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

        json_candidate = self._extract_json_object(cleaned)
        payload = json.loads(json_candidate)

        normalized = ExtractionResult.model_validate(payload)
        if normalized.context == "unknown":
            normalized.context = "The message does not contain enough cognitive evidence."
        return normalized

    def _extract_json_object(self, raw_response: str) -> str:
        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON object found in model response.")
        return raw_response[start : end + 1]

    def _fallback_result(self, text: str) -> dict[str, Any]:
        context = (
            LOW_SIGNAL_CONTEXT
            if len(text.split()) < 4 or self._is_low_signal_text(text)
            else f"The user message concerns: {text[:160]}"
        )
        return ExtractionResult(context=context).model_dump()

    def _prepare_text(self, text: str) -> str:
        cleaned_text = " ".join(text.strip().split())
        if len(cleaned_text) > MAX_EXTRACTION_INPUT_CHARS:
            logger.warning(
                "Extraction input exceeded %s characters and was truncated.",
                MAX_EXTRACTION_INPUT_CHARS,
            )
            return cleaned_text[:MAX_EXTRACTION_INPUT_CHARS].rstrip()
        return cleaned_text

    def _is_low_signal_text(self, text: str) -> bool:
        normalized_text = " ".join(text.strip().split())
        if not normalized_text:
            return True

        tokens = re.findall(r"[A-Za-z]+", normalized_text.lower())
        if not tokens:
            return True

        if len(tokens) == 1:
            token = tokens[0]
            vowel_count = sum(1 for char in token if char in "aeiou")
            if len(token) >= 8 and vowel_count <= 1:
                return True

        if len(tokens) <= 2:
            combined = "".join(tokens)
            vowel_ratio = (
                sum(1 for char in combined if char in "aeiou") / len(combined)
                if combined
                else 0.0
            )
            if len(combined) >= 10 and vowel_ratio < 0.25:
                return True

        return False


_default_extraction_service = ExtractionService()


def extract_cognition(text: str) -> dict[str, Any]:
    return _default_extraction_service.extract_cognition(text)
