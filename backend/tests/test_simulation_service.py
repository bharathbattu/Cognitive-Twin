from __future__ import annotations

import json
from typing import Any

from app.services.twin.simulation_service import SimulationService


class StubProfileService:
    def get_profile(self, session_id: str) -> dict[str, list[str]]:
        assert session_id == "session-42"
        return {
            "thinking_style": ["reflective and analytical"],
            "decision_traits": ["deliberate", "tradeoff-aware"],
            "preferences": ["clear tradeoffs", "low-clutter interfaces"],
            "contexts": ["launch planning", "team decisions"],
        }


class StubMemoryService:
    def retrieve_relevant_experiences(self, session_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        assert session_id == "session-42"
        assert top_k == 5
        return [
            {
                "id": "memory-1",
                "text": "I delayed a launch before when the tradeoffs felt unclear, and it paid off.",
                "role": "user",
                "metadata": {"context": "launch retrospective"},
                "relevance_rank": 1,
            },
            {
                "id": "memory-2",
                "text": "I prefer calm plans over rushed execution when multiple teams are involved.",
                "role": "user",
                "metadata": {"context": "cross-functional planning"},
                "relevance_rank": 2,
            },
        ]


class StubOpenRouterService:
    def __init__(self, responses: list[str]) -> None:
        self.client = object()
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def call_model_sync(
        self,
        task_type: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        self.calls.append(
            {
                "task_type": task_type,
                "messages": messages,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        return self.responses.pop(0)


def test_simulate_decision_uses_profile_and_memories_in_prompt() -> None:
    openrouter_service = StubOpenRouterService(
        [
            json.dumps(
                {
                    "decision": "I would delay the launch by a week.",
                    "reasoning": (
                        "I am deliberate and tradeoff-aware, and based on past experience delaying when "
                        "the tradeoffs were unclear paid off."
                    ),
                }
            )
        ]
    )
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=StubMemoryService(),  # type: ignore[arg-type]
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        max_retries=1,
    )

    result = service.simulate_decision("session-42", "Should I delay the launch by a week to reduce risk?")

    assert result["decision"] == "The user would delay the launch by a week."
    assert "deliberate" in result["reasoning"]
    assert "I " not in f"{result['decision']} {result['reasoning']}"
    assert " my " not in f" {result['decision']} {result['reasoning']} ".lower()

    request = openrouter_service.calls[0]
    system_prompt = request["messages"][0]["content"]
    user_prompt = request["messages"][1]["content"]

    assert request["task_type"] == "simulation"
    assert request["response_format"] == {"type": "json_object"}
    assert "You are simulating a specific user's thinking" in system_prompt
    assert "thinking_style: reflective and analytical" in system_prompt
    assert "decision_traits: deliberate, tradeoff-aware" in system_prompt
    assert "preferences: clear tradeoffs, low-clutter interfaces" in system_prompt
    assert "Past Behavior Examples:" in system_prompt
    assert "I delayed a launch before when the tradeoffs felt unclear" in system_prompt
    assert "You must explicitly reference at least one exact trait phrase from the profile in the reasoning." in system_prompt
    assert "If the simulated decision contradicts past behavior, explain why the current situation justifies that deviation." in system_prompt
    assert 'Respond strictly in third-person. Do NOT use first-person pronouns like "I", "me", or "my".' in system_prompt
    assert "No generic advice, no generic motivational language" in system_prompt
    assert "never expose memory ids, UUIDs, or bracketed internal references" in system_prompt
    assert "Example input" in system_prompt
    assert "Example output" in system_prompt
    assert "Return only valid JSON" in system_prompt
    assert "Scenario: Should I delay the launch by a week to reduce risk?" in user_prompt


def test_simulate_decision_retries_after_invalid_json() -> None:
    openrouter_service = StubOpenRouterService(
        [
            "not valid json",
            json.dumps(
                {
                    "decision": "I would wait one more day before deciding.",
                    "reasoning": (
                        "My reflective and analytical style makes me slow down when the tradeoffs are unclear, "
                        "and based on past experience taking a little more time has helped before."
                    ),
                }
            ),
        ]
    )
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=StubMemoryService(),  # type: ignore[arg-type]
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        max_retries=2,
    )

    result = service.simulate_decision("session-42", "Should I delay the launch by a week to reduce risk?")

    assert result["decision"] == "The user would wait one more day before deciding."
    assert len(openrouter_service.calls) == 2
    assert "invalid JSON, too generic, or violated the grounding rules" in openrouter_service.calls[1]["messages"][1]["content"]
    assert "reference past behavior naturally" in openrouter_service.calls[1]["messages"][1]["content"]


def test_simulate_decision_retries_when_output_is_too_generic() -> None:
    openrouter_service = StubOpenRouterService(
        [
            json.dumps(
                {
                    "decision": "It depends.",
                    "reasoning": "It depends on the situation and I need more context.",
                }
            ),
            json.dumps(
                {
                    "decision": "I would delay the launch by a day.",
                    "reasoning": (
                        "My reflective and analytical style makes me slow down, and based on past experience waiting "
                        "briefly when the tradeoffs feel unclear has paid off before."
                    ),
                }
            ),
        ]
    )
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=StubMemoryService(),  # type: ignore[arg-type]
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        max_retries=2,
    )

    result = service.simulate_decision("session-42", "Should I delay the launch by a week to reduce risk?")

    assert result["decision"] == "The user would delay the launch by a day."
    assert len(openrouter_service.calls) == 2
    assert "Retry with stronger grounding" in openrouter_service.calls[1]["messages"][1]["content"]


def test_simulate_decision_returns_structured_fallback_without_openrouter() -> None:
    openrouter_service = StubOpenRouterService([])
    openrouter_service.client = None
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=StubMemoryService(),  # type: ignore[arg-type]
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        max_retries=1,
    )

    result = service.simulate_decision("session-42", "Should I delay the launch by a week to reduce risk?")

    assert set(result) == {"decision", "reasoning"}
    assert result["decision"]
    assert "reflective and analytical" in result["reasoning"]
    assert "tradeoffs felt unclear" in result["reasoning"]
    assert "[" not in result["reasoning"]


def test_simulate_decision_returns_structured_fallback_for_empty_input() -> None:
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=StubMemoryService(),  # type: ignore[arg-type]
        openrouter_service=StubOpenRouterService([]),  # type: ignore[arg-type]
        max_retries=1,
    )

    result = service.simulate_decision("session-42", "   ")

    assert result == {
        "decision": "The user would pause until the scenario is concrete enough to evaluate.",
        "reasoning": "The user cannot simulate a consistent decision without a specific situation to react to.",
    }


def test_simulate_decision_returns_structured_fallback_for_low_signal_input() -> None:
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=StubMemoryService(),  # type: ignore[arg-type]
        openrouter_service=StubOpenRouterService([]),  # type: ignore[arg-type]
        max_retries=1,
    )

    result = service.simulate_decision("session-42", "asdfghjkl")

    assert result == {
        "decision": "The user would pause until the situation is clearer.",
        "reasoning": "The scenario does not provide enough grounded detail for a reliable simulation.",
    }


def test_simulate_decision_truncates_long_input_before_request() -> None:
    openrouter_service = StubOpenRouterService(
        [
            json.dumps(
                {
                    "decision": "I would delay the launch by a week.",
                    "reasoning": (
                        "My reflective and analytical style makes me cautious, and based on past experience delaying "
                        "when the tradeoffs were unclear has paid off."
                    ),
                }
            )
        ]
    )
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=StubMemoryService(),  # type: ignore[arg-type]
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        max_retries=1,
    )

    long_scenario = "a" * 6000
    result = service.simulate_decision("session-42", long_scenario)

    assert result["decision"] == "The user would delay the launch by a week."
    assert len(openrouter_service.calls[0]["messages"][1]["content"]) < 5400


def test_simulate_decision_returns_debug_payload_only_when_requested() -> None:
    openrouter_service = StubOpenRouterService(
        [
            json.dumps(
                {
                    "decision": "I would delay the launch by a week.",
                    "reasoning": (
                        "My reflective and analytical style makes me pause, and based on past experience waiting "
                        "helped when the tradeoffs felt unclear."
                    ),
                }
            )
        ]
    )
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=StubMemoryService(),  # type: ignore[arg-type]
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        max_retries=1,
    )

    result = service.simulate_decision(
        "session-42",
        "Should I delay the launch by a week to reduce risk?",
        debug=True,
    )

    assert result["decision"] == "The user would delay the launch by a week."
    assert result["debug"] == {
        "used_traits": ["reflective and analytical"],
        "used_memories": [
            {
                "id": "memory-1",
                "text": "I delayed a launch before when the tradeoffs felt unclear, and it paid off.",
                "context": "launch retrospective",
                "relevance_rank": 1,
            }
        ],
        "profile_snapshot": {
            "thinking_style": ["reflective and analytical"],
            "decision_traits": ["deliberate", "tradeoff-aware"],
            "preferences": ["clear tradeoffs", "low-clutter interfaces"],
            "contexts": ["launch planning", "team decisions"],
        },
    }


def test_simulate_decision_sanitizes_internal_memory_ids_from_reasoning() -> None:
    openrouter_service = StubOpenRouterService(
        [
            json.dumps(
                {
                    "decision": "I would delay the launch by a week.",
                    "reasoning": (
                        "My reflective and analytical style makes me pause, and [371208ac-9729-43df-8b0a-123456789abc] "
                        "shows that waiting helped when the tradeoffs felt unclear."
                    ),
                }
            )
        ]
    )
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=StubMemoryService(),  # type: ignore[arg-type]
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        max_retries=1,
    )

    result = service.simulate_decision("session-42", "Should I delay the launch by a week to reduce risk?")

    assert "371208ac-9729-43df-8b0a-123456789abc" not in result["reasoning"]
    assert "[" not in result["reasoning"]
    assert "the user's past experience" in result["reasoning"]
    assert "I " not in f"{result['decision']} {result['reasoning']}"


def test_simulate_decision_strips_markdown_and_list_formatting() -> None:
    openrouter_service = StubOpenRouterService(
        [
            json.dumps(
                {
                    "decision": "**I would delay the launch by a week.**",
                    "reasoning": (
                        "1. **My reflective and analytical style** makes me pause, and based on past experience "
                        "waiting helped when the tradeoffs felt unclear."
                    ),
                }
            )
        ]
    )
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=StubMemoryService(),  # type: ignore[arg-type]
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        max_retries=1,
    )

    result = service.simulate_decision("session-42", "Should I delay the launch by a week to reduce risk?")

    assert "**" not in result["decision"]
    assert "**" not in result["reasoning"]
    assert "1." not in result["reasoning"]
    assert "The user would delay the launch by a week." == result["decision"]


def test_simulate_decision_masks_uuid_in_debug_memory_payload() -> None:
    class UuidMemoryService(StubMemoryService):
        def retrieve_relevant_experiences(
            self,
            session_id: str,
            query: str,
            top_k: int = 5,
        ) -> list[dict[str, Any]]:
            assert session_id == "session-42"
            assert top_k == 5
            return [
                {
                    "id": "371208ac-9729-43df-8b0a-123456789abc",
                    "text": "I delayed a launch before when the tradeoffs felt unclear, and it paid off.",
                    "role": "user",
                    "metadata": {"context": "launch retrospective"},
                    "relevance_rank": 1,
                }
            ]

    openrouter_service = StubOpenRouterService(
        [
            json.dumps(
                {
                    "decision": "I would delay the launch by a week.",
                    "reasoning": (
                        "My reflective and analytical style makes me pause, and based on past experience waiting "
                        "helped when the tradeoffs felt unclear."
                    ),
                }
            )
        ]
    )
    service = SimulationService(
        profile_service=StubProfileService(),  # type: ignore[arg-type]
        memory_service=UuidMemoryService(),  # type: ignore[arg-type]
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        max_retries=1,
    )

    result = service.simulate_decision(
        "session-42",
        "Should I delay the launch by a week to reduce risk?",
        debug=True,
    )

    used_memories = result.get("debug", {}).get("used_memories", [])
    assert len(used_memories) == 1
    assert used_memories[0]["id"] == "memory-reference"
