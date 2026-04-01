from __future__ import annotations

import asyncio

from app.models.schemas.chat import ChatRequest
from app.services.twin.chat_service import ChatService, clean_response


class StubMemoryService:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def recall(self, session_id: str, query: str, top_k: int = 5) -> list[dict]:
        return [{"id": "memory-1", "text": "prior context", "role": "memory", "metadata": {}}]

    def remember(self, session_id: str, text: str, metadata: dict | None = None, role: str = "memory") -> None:
        self.records.append(
            {
                "session_id": session_id,
                "text": text,
                "metadata": metadata or {},
                "role": role,
            }
        )

    def list_memories(self, session_id: str):
        class _MemoryList:
            def __init__(self, items: list[dict]) -> None:
                self.items = items

            def model_dump(self, mode: str = "json") -> dict:
                return {"session_id": session_id, "count": len(self.items), "items": self.items}

        items = [record for record in self.records if record["session_id"] == session_id]
        return _MemoryList(items)


class StubOpenRouterService:
    async def generate_reply(self, message: str, memories: list[dict]) -> str:
        return f"reply to: {message} ({len(memories)} memories)"


class FailingOpenRouterService:
    async def generate_reply(self, message: str, memories: list[dict]) -> str:
        raise RuntimeError("openrouter unavailable")


class StubExtractionService:
    def extract_cognition(self, text: str) -> dict:
        return {
            "thinking_style": "reflective and analytical",
            "decision_traits": ["deliberate", "tradeoff-aware"],
            "preferences": ["clear tradeoffs"],
            "context": f"The user is discussing: {text}",
        }


class StubProfileService:
    def __init__(self) -> None:
        self.updated_calls: list[tuple[str, dict]] = []

    def update_profile(self, session_id: str, extracted_data: dict) -> dict:
        self.updated_calls.append((session_id, extracted_data))
        return {
            "thinking_style": ["reflective and analytical"],
            "decision_traits": ["deliberate", "tradeoff-aware"],
            "preferences": ["clear tradeoffs"],
            "contexts": ["The user is discussing a decision process."],
        }

    def build_profile(self, session_id: str):
        class _Profile:
            def model_dump(self, mode: str = "json") -> dict:
                return {
                    "session_id": session_id,
                    "summary": "profile summary",
                    "memory_count": 2,
                    "latest_topics": ["decision process"],
                    "twin_status": "training",
                }

        return _Profile()


class StubRealtimeEventService:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def publish(self, session_id: str, event_type: str, data: dict) -> None:
        self.events.append((session_id, event_type, data))


def test_chat_service_runs_extraction_and_profile_update() -> None:
    memory_service = StubMemoryService()
    profile_service = StubProfileService()
    realtime_event_service = StubRealtimeEventService()
    chat_service = ChatService(
        memory_service=memory_service,  # type: ignore[arg-type]
        openrouter_service=StubOpenRouterService(),  # type: ignore[arg-type]
        extraction_service=StubExtractionService(),  # type: ignore[arg-type]
        profile_service=profile_service,  # type: ignore[arg-type]
        realtime_event_service=realtime_event_service,  # type: ignore[arg-type]
    )

    response = asyncio.run(
        chat_service.chat(
            ChatRequest(
                message="I compare options carefully before choosing.",
                session_id="session-123",
                top_k=3,
            )
        )
    )

    assert response.reply.startswith("reply to:")
    assert profile_service.updated_calls[0][0] == "session-123"
    assert profile_service.updated_calls[0][1]["thinking_style"] == "reflective and analytical"

    extraction_records = [record for record in memory_service.records if record["role"] == "cognitive_extraction"]
    assert len(extraction_records) == 1
    assert extraction_records[0]["metadata"]["extraction"]["thinking_style"] == "reflective and analytical"

    user_records = [record for record in memory_service.records if record["role"] == "user"]
    assistant_records = [record for record in memory_service.records if record["role"] == "assistant"]
    assert len(user_records) == 1
    assert len(assistant_records) == 1
    assert [event_type for _session_id, event_type, _payload in realtime_event_service.events] == [
        "memory_update",
        "profile_update",
    ]


def test_chat_service_returns_controlled_reply_when_openrouter_fails() -> None:
    memory_service = StubMemoryService()
    profile_service = StubProfileService()
    realtime_event_service = StubRealtimeEventService()
    chat_service = ChatService(
        memory_service=memory_service,  # type: ignore[arg-type]
        openrouter_service=FailingOpenRouterService(),  # type: ignore[arg-type]
        extraction_service=StubExtractionService(),  # type: ignore[arg-type]
        profile_service=profile_service,  # type: ignore[arg-type]
        realtime_event_service=realtime_event_service,  # type: ignore[arg-type]
    )

    response = asyncio.run(
        chat_service.chat(
            ChatRequest(
                message="I compare options carefully before choosing.",
                session_id="session-chat-fallback",
                top_k=3,
            )
        )
    )

    assert response.reply == "The AI service is temporarily unavailable. Please try again shortly."
    assert len([record for record in memory_service.records if record["role"] == "user"]) == 1
    assert len([record for record in memory_service.records if record["role"] == "assistant"]) == 1
    assert [event_type for _session_id, event_type, _payload in realtime_event_service.events] == [
        "memory_update",
        "profile_update",
    ]


def test_clean_response_removes_markdown_and_list_style() -> None:
    raw = (
        "1. **Risky opportunities over safe jobs**: You're willing to take risks.\n"
        "2. **Building things over corporate jobs**: You prefer creative work."
    )

    cleaned = clean_response(raw)

    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "1." not in cleaned
    assert "2." not in cleaned
    assert "risky opportunities over safe jobs" in cleaned.lower()
    assert "building things over corporate jobs" in cleaned.lower()


def test_clean_response_single_numbered_bold_item_case_one() -> None:
    raw = "1. **Risky opportunities over safe jobs**"
    assert clean_response(raw) == "Risky opportunities over safe jobs"


def test_clean_response_single_numbered_bold_item_case_two() -> None:
    raw = "2. **Building things over corporate jobs**"
    assert clean_response(raw) == "Building things over corporate jobs"
