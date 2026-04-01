from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.services.ai.openrouter_service import OpenRouterService


class AsyncFailingOpenRouterService(OpenRouterService):
    def __init__(self, failure: Exception) -> None:
        super().__init__()
        self.failure = failure
        self.attempts = 0

    async def _request_completion(
        self,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
    ) -> str:
        self.attempts += 1
        raise self.failure


class SyncResponseStub:
    def __init__(self, content: Any) -> None:
        self.choices = [
            type(
                "Choice",
                (),
                {"message": type("Message", (), {"content": content})()},
            )()
        ]


class SyncClientStub:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_async_call_model_retries_network_failures_and_returns_controlled_fallback() -> None:
    service = AsyncFailingOpenRouterService(httpx.ReadTimeout("timed out"))

    result = asyncio.run(
        service.call_model(
            task_type="chat",
            messages=[{"role": "user", "content": "hello"}],
        )
    )

    assert result == "The AI service is temporarily unavailable. Please try again shortly."
    assert service.attempts == 3


def test_call_model_sync_retries_invalid_responses_and_returns_controlled_json_fallback() -> None:
    service = OpenRouterService()
    service.client = type(
        "Client",
        (),
        {
            "chat": type(
                "Chat",
                (),
                {
                    "completions": SyncClientStub(
                        [
                            SyncResponseStub(None),
                            RuntimeError("network failed"),
                            SyncResponseStub(None),
                        ]
                    )
                },
            )()
        },
    )()

    result = service.call_model_sync(
        task_type="simulation",
        messages=[{"role": "user", "content": "simulate"}],
        response_format={"type": "json_object"},
    )

    assert json.loads(result) == {
        "decision": "I would pause until the AI service is available again.",
        "reasoning": "The simulation model is temporarily unavailable, so this response is a controlled fallback.",
    }
