import json
from collections.abc import Iterator
from typing import Any, cast

from app.services.twin.extraction_service import ExtractionService


class StubExtractionService(ExtractionService):
    def __init__(self, responses: Iterator[str], max_retries: int = 3) -> None:
        super().__init__(max_retries=max_retries)
        self.responses = responses
        self.openrouter_service.client = cast(Any, object())

    def _request_extraction(self, *args: Any, **kwargs: Any) -> str:
        return next(self.responses)


def test_extract_cognition_returns_fallback_for_empty_text() -> None:
    service = ExtractionService(max_retries=1)

    result = service.extract_cognition("   ")

    assert result == {
        "thinking_style": "unknown",
        "decision_traits": [],
        "preferences": [],
        "context": "The message does not contain enough cognitive evidence.",
    }


def test_extract_cognition_cleans_markdown_wrapped_json() -> None:
    service = StubExtractionService(
        iter(
            [
                """```json
                {"thinking_style":"analytical","decision_traits":["deliberate"],"preferences":["clear options"],"context":"The user describes a structured decision process."}
                ```"""
            ]
        ),
        max_retries=1,
    )

    result = service.extract_cognition("I compare options carefully.")

    assert result["thinking_style"] == "analytical"
    assert result["decision_traits"] == ["deliberate"]


def test_extract_cognition_retries_after_invalid_json() -> None:
    service = StubExtractionService(
        iter(
            [
                "not valid json",
                json.dumps(
                    {
                        "thinking_style": "intuitive and action-oriented",
                        "decision_traits": ["fast-moving", "experiment-driven"],
                        "preferences": ["real-world testing"],
                        "context": "The user describes how they prefer to act on ideas quickly.",
                    }
                ),
            ]
        ),
        max_retries=2,
    )

    result = service.extract_cognition("If it feels right, I move quickly and test it live.")

    assert result["thinking_style"] == "intuitive and action-oriented"
    assert result["decision_traits"] == ["fast-moving", "experiment-driven"]


def test_extract_cognition_returns_safe_fallback_after_exhausting_invalid_json() -> None:
    service = StubExtractionService(iter(["not json", "still not json"]), max_retries=2)

    result = service.extract_cognition("I like risky startups but hate careless decisions.")

    assert result == {
        "thinking_style": "unknown",
        "decision_traits": [],
        "preferences": [],
        "context": "The user message concerns: I like risky startups but hate careless decisions.",
    }


def test_extract_cognition_returns_safe_fallback_for_low_signal_text() -> None:
    service = ExtractionService(max_retries=1)

    result = service.extract_cognition("asdfghjkl")

    assert result == {
        "thinking_style": "unknown",
        "decision_traits": [],
        "preferences": [],
        "context": "The message does not contain enough cognitive evidence.",
    }


def test_extract_cognition_truncates_long_input_before_request() -> None:
    class CapturingExtractionService(ExtractionService):
        def __init__(self) -> None:
            super().__init__(max_retries=1)
            self.captured_text = ""
            self.openrouter_service.client = cast(Any, object())

        def _request_extraction(self, text: str, *args: Any, **kwargs: Any) -> str:
            self.captured_text = text
            return json.dumps(
                {
                    "thinking_style": "analytical",
                    "decision_traits": ["deliberate"],
                    "preferences": ["clear options"],
                    "context": "The user describes a structured decision process.",
                }
            )

    service = CapturingExtractionService()

    result = service.extract_cognition("a" * 6000)

    assert result["thinking_style"] == "analytical"
    assert len(service.captured_text) == 5000
