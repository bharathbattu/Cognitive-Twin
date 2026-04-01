from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator

from app.services.ai.openrouter_service import OpenRouterService
from app.services.memory.memory_service import MemoryService
from app.services.twin.profile_service import DEPLOYED_STATUS, ProfileService, TRAINING_STATUS

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
DEFAULT_REASONING = "Grounded evidence from the user's past behavior is too limited to simulate this confidently."
MAX_SCENARIO_CHARS = 5000
GENERIC_REASONING_PHRASES = (
    "it depends",
    "depends on the situation",
    "need more context",
    "not enough information",
    "hard to say",
    "cannot determine",
)
MEMORY_GROUNDING_PHRASES = (
    "in similar situations",
    "in the past",
    "from past experience",
    "based on the user's past behavior",
    "based on the user's past preferences",
    "based on your past preferences",
    "based on past experience",
    "the user's past experience",
    "your past experience",
    "the user has tended to",
    "the user usually",
    "they usually",
    "you have tended to",
    "you usually",
    "you've usually",
    "what you've done before",
    "what you have done before",
)
MEMORY_REFERENCE_PATTERN = re.compile(
    r"\[(?:memory-\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]",
    flags=re.IGNORECASE,
)
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    flags=re.IGNORECASE,
)
WORD_PATTERN = re.compile(r"[a-z0-9']+")
FIRST_PERSON_PATTERN = re.compile(r"\b(?:i|me|my|mine|myself)\b|\bi['’](?:m|d|ve|ll)\b", flags=re.IGNORECASE)
FIRST_PERSON_REPLACEMENTS = (
    (re.compile(r"\bi['’]m\b", flags=re.IGNORECASE), "the user is"),
    (re.compile(r"\bi am\b", flags=re.IGNORECASE), "the user is"),
    (re.compile(r"\bi was\b", flags=re.IGNORECASE), "the user was"),
    (re.compile(r"\bi['’]ve\b", flags=re.IGNORECASE), "the user has"),
    (re.compile(r"\bi have\b", flags=re.IGNORECASE), "the user has"),
    (re.compile(r"\bi had\b", flags=re.IGNORECASE), "the user had"),
    (re.compile(r"\bi['’]d\b", flags=re.IGNORECASE), "the user would"),
    (re.compile(r"\bi would\b", flags=re.IGNORECASE), "the user would"),
    (re.compile(r"\bi['’]ll\b", flags=re.IGNORECASE), "the user will"),
    (re.compile(r"\bi will\b", flags=re.IGNORECASE), "the user will"),
    (re.compile(r"\bi cannot\b", flags=re.IGNORECASE), "the user cannot"),
    (re.compile(r"\bi can['’]t\b", flags=re.IGNORECASE), "the user cannot"),
    (re.compile(r"\bi don['’]t\b", flags=re.IGNORECASE), "the user does not"),
    (re.compile(r"\bi do\b", flags=re.IGNORECASE), "the user does"),
    (re.compile(r"\bi tend to prefer\b", flags=re.IGNORECASE), "the user tends to prefer"),
    (re.compile(r"\bi tend to\b", flags=re.IGNORECASE), "the user tends to"),
    (re.compile(r"\bi usually\b", flags=re.IGNORECASE), "the user usually"),
    (re.compile(r"\bi prefer\b", flags=re.IGNORECASE), "the user prefers"),
    (re.compile(r"\bi like\b", flags=re.IGNORECASE), "the user likes"),
    (re.compile(r"\bi think\b", flags=re.IGNORECASE), "the user thinks"),
    (re.compile(r"\bi need\b", flags=re.IGNORECASE), "the user needs"),
    (re.compile(r"\bi want\b", flags=re.IGNORECASE), "the user wants"),
    (re.compile(r"\bi choose\b", flags=re.IGNORECASE), "the user chooses"),
    (re.compile(r"\bi chose\b", flags=re.IGNORECASE), "the user chose"),
    (re.compile(r"\bmy preference\b", flags=re.IGNORECASE), "the user's preference"),
    (re.compile(r"\bmy preferences\b", flags=re.IGNORECASE), "the user's preferences"),
    (re.compile(r"\bmy\b", flags=re.IGNORECASE), "the user's"),
    (re.compile(r"\bmine\b", flags=re.IGNORECASE), "the user's"),
    (re.compile(r"\bmyself\b", flags=re.IGNORECASE), "the user"),
    (re.compile(r"\bme\b", flags=re.IGNORECASE), "the user"),
    (re.compile(r"\bi\b", flags=re.IGNORECASE), "the user"),
)


class SimulationResult(BaseModel):
    decision: str
    reasoning: str

    @field_validator("decision", "reasoning", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("Simulation output fields must be strings.")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Simulation output fields cannot be empty.")
        return normalized


class SimulationService:
    def __init__(
        self,
        profile_service: ProfileService,
        memory_service: MemoryService,
        openrouter_service: OpenRouterService | None = None,
        max_retries: int = 3,
        memory_top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self.profile_service = profile_service
        self.memory_service = memory_service
        self.openrouter_service = openrouter_service or OpenRouterService()
        self.max_retries = max_retries
        self.memory_top_k = memory_top_k

    def simulate_decision(self, session_id: str, scenario: str, debug: bool = False) -> dict[str, Any]:
        cleaned_scenario = self._prepare_scenario(scenario)
        if not cleaned_scenario:
            base_result: dict[str, Any] = self._controlled_result(
                decision="The user would pause until the scenario is concrete enough to evaluate.",
                reasoning="The user cannot simulate a consistent decision without a specific situation to react to.",
            )
            if debug:
                base_result["debug"] = {
                    "used_traits": [],
                    "used_memories": [],
                    "profile_snapshot": {},
                }
            return base_result

        if self._is_low_signal_scenario(cleaned_scenario):
            logger.info("Received low-signal simulation scenario. Returning deterministic fallback.")
            fallback_result = self._controlled_result(
                decision="The user would pause until the situation is clearer.",
                reasoning="The scenario does not provide enough grounded detail for a reliable simulation.",
            )
            return self._attach_debug_data(fallback_result, {}, [], debug)

        profile = self.profile_service.get_profile(session_id)
        twin_status = self._resolve_twin_status(session_id)
        memories = self.memory_service.retrieve_relevant_experiences(
            session_id=session_id,
            query=cleaned_scenario,
            top_k=self.memory_top_k,
        )

        if self.openrouter_service.client is None:
            logger.warning("OpenRouter client is not configured. Returning deterministic simulation fallback.")
            fallback_result = self._fallback_result(profile, memories, cleaned_scenario, twin_status)
            return self._attach_debug_data(fallback_result, profile, memories, debug)

        last_error: Exception | None = None
        last_raw_response = ""

        for attempt in range(1, self.max_retries + 1):
            logger.info("Decision simulation attempt %s/%s", attempt, self.max_retries)
            try:
                raw_response = self._request_simulation(
                    scenario=cleaned_scenario,
                    profile=profile,
                    memories=memories,
                    twin_status=twin_status,
                    attempt=attempt,
                    previous_raw_response=last_raw_response,
                    previous_error=last_error,
                )
                last_raw_response = raw_response
                logger.debug("Raw simulation response: %s", raw_response[:1000])
                parsed = self._parse_response(raw_response)
                self._validate_grounding(parsed, profile, memories, twin_status)
                return self._attach_debug_data(parsed.model_dump(), profile, memories, debug)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                logger.warning("Decision simulation parsing/validation failed on attempt %s: %s", attempt, exc)
            except Exception as exc:  # pragma: no cover - depends on network/runtime state
                last_error = exc
                logger.exception("Decision simulation model call failed on attempt %s", attempt)

        logger.error("Decision simulation failed after %s attempts. Using deterministic fallback.", self.max_retries)
        fallback_result = self._fallback_result(profile, memories, cleaned_scenario, twin_status)
        return self._attach_debug_data(fallback_result, profile, memories, debug)

    def _request_simulation(
        self,
        scenario: str,
        profile: dict[str, list[str]],
        memories: list[dict[str, Any]],
        twin_status: str,
        attempt: int,
        previous_raw_response: str,
        previous_error: Exception | None,
    ) -> str:
        if self.openrouter_service.client is None:
            raise RuntimeError("OpenRouter client is not configured.")

        retry_note = ""
        if attempt > 1:
            retry_note = (
                "\n\nYour previous output was invalid JSON, too generic, or violated the grounding rules. "
                f"Error: {previous_error}. Previous output: {previous_raw_response[:600]}"
                "\nRetry with stronger grounding: include one exact trait phrase and reference past behavior naturally."
            )

        return self.openrouter_service.call_model_sync(
            task_type="simulation",
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self._build_system_prompt(profile, memories, twin_status)},
                {
                    "role": "user",
                    "content": (
                        "Simulate the user's likely decision for the following scenario.\n"
                        "Return exactly one JSON object matching the schema.\n"
                        f"Scenario: {scenario}{retry_note}"
                    ),
                },
            ],
        )

    def _build_system_prompt(self, profile: dict[str, list[str]], memories: list[dict[str, Any]], twin_status: str) -> str:
        thinking_style = ", ".join(profile.get("thinking_style") or ["unknown"])
        decision_traits = ", ".join(profile.get("decision_traits") or ["unknown"])
        preferences = ", ".join(profile.get("preferences") or ["unknown"])
        contexts = ", ".join(profile.get("contexts") or ["unknown"])
        memory_block = self._format_memories(memories)
        lifecycle_instruction = (
            "The twin is still in TRAINING. Evidence can be sparse, so mild extrapolation is allowed if you remain plausible."
            if twin_status == TRAINING_STATUS
            else "The twin is DEPLOYED. Prioritize consistency with dominant traits and do not contradict them unless memory evidence is strong."
        )

        return f"""
You are simulating a specific user's thinking.
You are not an assistant, coach, or advisor.
Respond as the user's likely decision, grounded only in the profile and memories below.
Respond strictly in third-person. Do NOT use first-person pronouns like "I", "me", or "my". Always refer to the user as "the user" or "they".

Known cognitive profile:
- twin_status: {twin_status}
- thinking_style: {thinking_style}
- decision_traits: {decision_traits}
- preferences: {preferences}
- recent_contexts: {contexts}

Past Behavior Examples:
{memory_block}

Rules:
1. Stay consistent with the user's profile and prior behavior.
1a. {lifecycle_instruction}
2. You must explicitly reference at least one exact trait phrase from the profile in the reasoning.
3. Use past memories as justification, but never expose memory ids, UUIDs, or bracketed internal references.
4. If the simulated decision contradicts past behavior, explain why the current situation justifies that deviation.
5. Do not hallucinate facts, biography, emotions, or history beyond the supplied profile and memories.
6. Do not sound like an AI assistant. No generic advice, no generic motivational language, no coaching tone, and no disclaimers like "as an AI".
7. If evidence is thin, say the evidence is limited, but still choose the most plausible decision.
8. Tie the reasoning to specific traits and specific memories. Avoid vague summaries.
9. Return only valid JSON.
10. Do not return markdown.
11. Do not return code fences.
12. Do not return any text before or after the JSON object.

Output schema:
{{
  "decision": "string",
  "reasoning": "string"
}}

Example input:
Scenario: My teammate wants to ship now even though the tradeoffs still feel muddy.

Example output:
{{"decision":"The user would slow the launch down until the tradeoffs are clearer.","reasoning":"The user's reflective and analytical style makes them pause when the tradeoffs are still muddy, and based on the user's past experience delaying in that kind of situation has paid off."}}
""".strip()

    def _format_memories(self, memories: list[dict[str, Any]]) -> str:
        if not memories:
            return "- No relevant memories were retrieved."

        lines: list[str] = []
        for index, memory in enumerate(memories[: self.memory_top_k], start=1):
            memory_id = str(memory.get("id") or f"memory-{index}")
            text = " ".join(str(memory.get("text", "")).strip().split()) or "No text provided."
            context = ""
            metadata = memory.get("metadata")
            if isinstance(metadata, dict):
                context_value = metadata.get("context")
                if isinstance(context_value, str) and context_value.strip():
                    context = f" | context: {' '.join(context_value.strip().split())}"
            lines.append(f"- [{memory_id}] {text}{context}")
        return "\n".join(lines)

    def _parse_response(self, raw_response: str) -> SimulationResult:
        cleaned = raw_response.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

        json_candidate = self._extract_json_object(cleaned)
        payload = json.loads(json_candidate)
        parsed = SimulationResult.model_validate(payload)
        return SimulationResult(
            decision=self._sanitize_simulation_text(parsed.decision),
            reasoning=self._sanitize_reasoning(parsed.reasoning),
        )

    def _extract_json_object(self, raw_response: str) -> str:
        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON object found in model response.")
        return raw_response[start : end + 1]

    def _validate_grounding(
        self,
        result: SimulationResult,
        profile: dict[str, list[str]],
        memories: list[dict[str, Any]],
        twin_status: str,
    ) -> None:
        combined_text = f"{result.decision} {result.reasoning}".lower()
        self._ensure_third_person(result)
        self._ensure_non_assistant_tone(combined_text)

        trait_phrases = [
            value.lower()
            for key in ("thinking_style", "decision_traits", "preferences")
            for value in profile.get(key, [])
            if isinstance(value, str) and value.strip()
        ]
        has_trait_reference = any(trait in combined_text for trait in trait_phrases)
        if trait_phrases and twin_status == DEPLOYED_STATUS and not has_trait_reference:
            raise ValueError("Reasoning must explicitly reference at least one cognitive trait from the profile.")
        if trait_phrases and twin_status == TRAINING_STATUS and memories and not has_trait_reference:
            raise ValueError("Training simulations with memory evidence must still reference at least one cognitive trait.")

        if memories and not self._has_memory_grounding(result.reasoning):
            raise ValueError("Reasoning must reference past behavior naturally without exposing internal ids.")

        self._ensure_not_generic(result)

    def _ensure_non_assistant_tone(self, combined_text: str) -> None:
        banned_phrases = (
            "as an ai",
            "as a language model",
            "i cannot provide",
            "i can't provide",
            "i do not have personal",
            "you should",
            "i recommend that you",
            "my advice is",
        )
        if any(phrase in combined_text for phrase in banned_phrases):
            raise ValueError("Simulation drifted into assistant-style language.")

    def _ensure_not_generic(self, result: SimulationResult) -> None:
        combined_text = f"{result.decision} {result.reasoning}".lower()
        if len(result.reasoning.split()) < 12:
            raise ValueError("Simulation reasoning was too short to be reliable.")
        if any(phrase in combined_text for phrase in GENERIC_REASONING_PHRASES):
            raise ValueError("Simulation response was too generic.")
        if MEMORY_REFERENCE_PATTERN.search(result.reasoning) or UUID_PATTERN.search(result.reasoning):
            raise ValueError("Simulation response exposed an internal memory identifier.")

    def _ensure_third_person(self, result: SimulationResult) -> None:
        if FIRST_PERSON_PATTERN.search(result.decision) or FIRST_PERSON_PATTERN.search(result.reasoning):
            raise ValueError("Simulation response must remain in third-person.")

    def _attach_debug_data(
        self,
        result: dict[str, Any],
        profile: dict[str, list[str]],
        memories: list[dict[str, Any]],
        debug: bool,
    ) -> dict[str, Any]:
        if not debug:
            return result

        debug_payload = self._build_debug_payload(result, profile, memories)
        return {
            **result,
            "debug": debug_payload,
        }

    def _build_debug_payload(
        self,
        result: dict[str, Any],
        profile: dict[str, list[str]],
        memories: list[dict[str, Any]],
    ) -> dict[str, Any]:
        combined_text = " ".join(
            [
                " ".join(str(result.get("decision", "")).strip().split()),
                " ".join(str(result.get("reasoning", "")).strip().split()),
            ]
        ).lower()

        used_traits = [
            trait
            for key in ("thinking_style", "decision_traits", "preferences")
            for trait in profile.get(key, [])
            if isinstance(trait, str) and trait.strip() and trait.lower() in combined_text
        ]

        used_memories = [
            self._serialize_memory(memory)
            for memory in memories
            if self._memory_is_reflected_in_reasoning(combined_text, memory)
        ]

        return {
            "used_traits": used_traits,
            "used_memories": used_memories,
            "profile_snapshot": profile,
        }

    def _serialize_memory(self, memory: dict[str, Any]) -> dict[str, Any]:
        metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
        context = metadata.get("context") if isinstance(metadata, dict) else None
        raw_memory_id = str(memory.get("id", "")).strip()
        memory_id = "memory-reference" if UUID_PATTERN.fullmatch(raw_memory_id) else raw_memory_id
        serialized = {
            "id": memory_id,
            "text": " ".join(str(memory.get("text", "")).strip().split()),
            "context": " ".join(str(context).strip().split()) if isinstance(context, str) and context.strip() else "",
            "relevance_rank": memory.get("relevance_rank"),
        }
        return serialized

    def _fallback_result(
        self,
        profile: dict[str, list[str]],
        memories: list[dict[str, Any]],
        scenario: str,
        twin_status: str,
    ) -> dict[str, str]:
        traits = profile.get("decision_traits", [])
        thinking_style = profile.get("thinking_style", [])
        preferences = profile.get("preferences", [])

        if twin_status == TRAINING_STATUS:
            decision = "The user would test a small step first, then adapt based on what they learn."
        elif any(trait in {"deliberate", "tradeoff-aware", "option-comparing"} for trait in traits) or (
            thinking_style and "reflective" in thinking_style[0]
        ):
            decision = "The user would slow this down a bit and compare the tradeoffs before committing."
        elif any(trait in {"fast-moving", "experiment-driven", "speed-oriented"} for trait in traits):
            decision = "The user would run a small real-world test before making the full commitment."
        else:
            decision = "The user would make the call that feels most consistent with how they have handled similar situations before."

        reasoning_parts: list[str] = []
        if thinking_style:
            reasoning_parts.append(f"The user's {thinking_style[0]} style shapes how they react here.")
        reasoning_parts.append(
            "The twin is still training, so this prediction allows a little flexibility while keeping close to observed patterns."
            if twin_status == TRAINING_STATUS
            else "The twin is deployed, so the decision stays tightly aligned with stable cognitive traits."
        )
        if traits:
            reasoning_parts.append(
                f"The user usually leans on traits like {', '.join(traits[:3])} when making this kind of choice."
            )
        if preferences:
            reasoning_parts.append(f"The user also tends to prefer {', '.join(preferences[:2])}.")

        cited_memories: list[str] = []
        for memory in memories[:2]:
            memory_text = " ".join(str(memory.get("text", "")).strip().split())
            if memory_text:
                cited_memories.append(f"In similar situations before, the user has said things like: {memory_text}")
        if cited_memories:
            reasoning_parts.append(" ".join(cited_memories))
        else:
            reasoning_parts.append(DEFAULT_REASONING)

        reasoning_parts.append(f"The scenario the user is reacting to is: {scenario}")
        return self._controlled_result(
            decision=decision,
            reasoning=" ".join(reasoning_parts),
        )

    def _resolve_twin_status(self, session_id: str) -> str:
        get_status = getattr(self.profile_service, "get_twin_status", None)
        if callable(get_status):
            status = get_status(session_id)
            if status in {TRAINING_STATUS, DEPLOYED_STATUS}:
                return status
        return TRAINING_STATUS

    def _controlled_result(self, decision: str, reasoning: str) -> dict[str, str]:
        result = SimulationResult(
            decision=self._sanitize_simulation_text(decision),
            reasoning=self._sanitize_reasoning(reasoning),
        )
        self._ensure_third_person(result)
        return result.model_dump()

    def _prepare_scenario(self, scenario: str) -> str:
        cleaned_scenario = " ".join(scenario.strip().split())
        if len(cleaned_scenario) > MAX_SCENARIO_CHARS:
            logger.warning(
                "Simulation scenario exceeded %s characters and was truncated.",
                MAX_SCENARIO_CHARS,
            )
            return cleaned_scenario[:MAX_SCENARIO_CHARS].rstrip()
        return cleaned_scenario

    def _is_low_signal_scenario(self, scenario: str) -> bool:
        tokens = re.findall(r"[A-Za-z]+", scenario.lower())
        if not tokens:
            return True
        if len(tokens) == 1:
            token = tokens[0]
            vowel_count = sum(1 for char in token if char in "aeiou")
            if len(token) >= 8 and vowel_count <= 1:
                return True
        return False

    def _sanitize_reasoning(self, reasoning: str) -> str:
        sanitized = MEMORY_REFERENCE_PATTERN.sub("the user's past experience", reasoning)
        sanitized = UUID_PATTERN.sub("the user's past experience", sanitized)
        sanitized = re.sub(
            r"\bthe user's past experience\b(?:\s+the user's past experience\b)+",
            "the user's past experience",
            sanitized,
        )
        sanitized = self._sanitize_simulation_text(sanitized)
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        return sanitized

    def _sanitize_simulation_text(self, text: str) -> str:
        sanitized = " ".join(text.strip().split())
        sanitized = re.sub(r"\*\*(.*?)\*\*", r"\1", sanitized)
        sanitized = re.sub(r"\*", "", sanitized)
        sanitized = re.sub(r"```(?:json)?", "", sanitized, flags=re.IGNORECASE)
        sanitized = sanitized.replace("```", "")
        sanitized = re.sub(r"\b\d+\.\s*", "", sanitized)
        for pattern, replacement in FIRST_PERSON_REPLACEMENTS:
            sanitized = pattern.sub(replacement, sanitized)
        sanitized = re.sub(r"(^|[.!?]\s+)(the user)\b", lambda match: f"{match.group(1)}The user", sanitized)
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        return sanitized

    def _has_memory_grounding(self, reasoning: str) -> bool:
        lowered_reasoning = reasoning.lower()
        return any(phrase in lowered_reasoning for phrase in MEMORY_GROUNDING_PHRASES)

    def _memory_is_reflected_in_reasoning(self, combined_text: str, memory: dict[str, Any]) -> bool:
        memory_id = str(memory.get("id") or "").strip().lower()
        if memory_id and memory_id in combined_text:
            return True

        memory_tokens = {
            token
            for token in WORD_PATTERN.findall(str(memory.get("text", "")).lower())
            if len(token) > 4
        }
        if not memory_tokens:
            return False

        overlap = memory_tokens.intersection(set(WORD_PATTERN.findall(combined_text)))
        return len(overlap) >= 3


def simulate_decision(session_id: str, scenario: str, debug: bool = False) -> dict[str, Any]:
    from app.core.dependencies import get_memory_service, get_openrouter_service, get_profile_service

    service = SimulationService(
        profile_service=get_profile_service(),
        memory_service=get_memory_service(),
        openrouter_service=get_openrouter_service(),
    )
    return service.simulate_decision(session_id=session_id, scenario=scenario, debug=debug)
