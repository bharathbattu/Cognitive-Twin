from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.core.dependencies import get_memory_service, get_profile_service, get_realtime_event_service, get_simulation_service
from app.main import app


class StubSimulationService:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.response = response or {
            "decision": "The user would wait one more day before deciding.",
            "reasoning": "The user's reflective and analytical style makes them slow down when tradeoffs are unclear.",
        }
        self.error = error
        self.calls: list[tuple[str, str, bool]] = []

    def simulate_decision(self, session_id: str, scenario: str, debug: bool = False) -> dict[str, Any]:
        self.calls.append((session_id, scenario, debug))
        if self.error is not None:
            raise self.error
        return self.response


class StubProfileService:
    def __init__(self, transition_response: dict[str, Any]) -> None:
        self.transition_response = transition_response
        self.calls: list[str] = []

    def build_profile(self, session_id: str) -> Any:
        raise NotImplementedError

    def transition_lifecycle_if_deployed(self, session_id: str) -> dict[str, Any]:
        self.calls.append(session_id)
        return self.transition_response


class StubMemoryService:
    class _Entry:
        def __init__(self, entry_id: str, session_id: str, text: str, created_at: datetime) -> None:
            self.id = entry_id
            self.session_id = session_id
            self.text = text
            self.created_at = created_at
            self.role = "user"

    def __init__(self, user_texts: list[str] | None = None) -> None:
        self.remember_calls: list[dict[str, Any]] = []
        self.list_calls: list[str] = []
        self.user_entries = [
            self._Entry(
                entry_id=f"user-{index + 1}",
                session_id="",
                text=text,
                created_at=datetime.now(UTC),
            )
            for index, text in enumerate(user_texts or [])
        ]

    def remember(self, session_id: str, text: str, metadata: dict[str, Any] | None = None, role: str = "memory") -> None:
        self.remember_calls.append(
            {
                "session_id": session_id,
                "text": text,
                "metadata": metadata or {},
                "role": role,
            }
        )

    def get_memories(self, session_id: str, role: str | None = None, metadata_key: str | None = None) -> list[Any]:
        if role == "user":
            for entry in self.user_entries:
                entry.session_id = session_id
            return self.user_entries
        return []

    def list_memories(self, session_id: str) -> Any:
        self.list_calls.append(session_id)

        class _MemoryList:
            def model_dump(self, mode: str = "json") -> dict[str, Any]:
                return {
                    "session_id": session_id,
                    "count": 1,
                    "items": [],
                }

        return _MemoryList()


class StubRealtimeEventService:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    async def publish(self, session_id: str, event_type: str, data: dict[str, Any]) -> None:
        self.events.append((session_id, event_type, data))


def test_simulate_route_returns_structured_response() -> None:
    simulation_service = StubSimulationService()
    memory_service = StubMemoryService(
        user_texts=[
            "I test small bets before making major moves.",
            "I compare risk and upside when timing launches.",
        ]
    )
    realtime_service = StubRealtimeEventService()
    app.dependency_overrides[get_simulation_service] = lambda: simulation_service
    app.dependency_overrides[get_memory_service] = lambda: memory_service
    app.dependency_overrides[get_realtime_event_service] = lambda: realtime_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/twin/simulate",
        json={
            "session_id": "session-77",
            "scenario": "Should I delay the launch by a week to reduce risk?",
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            **simulation_service.response,
            "debug": None,
        },
        "error": None,
    }
    assert simulation_service.calls == [("session-77", "Should I delay the launch by a week to reduce risk?", False)]
    assert len(memory_service.remember_calls) == 1
    assert memory_service.remember_calls[0]["role"] == "memory"
    assert memory_service.remember_calls[0]["metadata"]["source"] == "simulation_engine"
    assert memory_service.remember_calls[0]["metadata"]["simulation"]["recent_user_interaction_count"] == 2
    assert len(memory_service.remember_calls[0]["metadata"]["simulation"]["recent_user_interactions"]) == 2
    assert memory_service.list_calls == ["session-77"]
    assert [event_type for _session_id, event_type, _data in realtime_service.events] == [
        "memory_update",
        "simulation_result",
    ]


def test_simulate_route_returns_debug_payload_when_requested() -> None:
    simulation_service = StubSimulationService(
        response={
            "decision": "The user would delay the launch.",
            "reasoning": "The user's reflective and analytical style makes them cautious here.",
            "debug": {
                "used_traits": ["reflective and analytical"],
                "used_memories": [{"id": "memory-1", "text": "I delayed a launch before.", "context": "retro", "relevance_rank": 1}],
                "profile_snapshot": {"thinking_style": ["reflective and analytical"]},
            },
        }
    )
    memory_service = StubMemoryService()
    realtime_service = StubRealtimeEventService()
    app.dependency_overrides[get_simulation_service] = lambda: simulation_service
    app.dependency_overrides[get_memory_service] = lambda: memory_service
    app.dependency_overrides[get_realtime_event_service] = lambda: realtime_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/twin/simulate",
        json={
            "session_id": "session-88",
            "scenario": "Should I delay the launch?",
            "debug": True,
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["debug"]["used_traits"] == ["reflective and analytical"]
    assert simulation_service.calls == [("session-88", "Should I delay the launch?", True)]
    assert memory_service.remember_calls[0]["metadata"]["simulation"]["debug"] is not None


def test_simulate_route_caps_recent_user_interactions_at_nine() -> None:
    simulation_service = StubSimulationService()
    memory_service = StubMemoryService(user_texts=[f"interaction-{index}" for index in range(1, 13)])
    realtime_service = StubRealtimeEventService()
    app.dependency_overrides[get_simulation_service] = lambda: simulation_service
    app.dependency_overrides[get_memory_service] = lambda: memory_service
    app.dependency_overrides[get_realtime_event_service] = lambda: realtime_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/twin/simulate",
        json={
            "session_id": "session-67",
            "scenario": "Should I run a pilot before full launch?",
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    interaction_snapshot = memory_service.remember_calls[0]["metadata"]["simulation"]["recent_user_interactions"]
    assert len(interaction_snapshot) == 9
    assert memory_service.remember_calls[0]["metadata"]["simulation"]["recent_user_interaction_count"] == 9
    assert interaction_snapshot[0]["text"] == "interaction-4"
    assert interaction_snapshot[-1]["text"] == "interaction-12"


def test_simulate_route_validates_request_payload() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/twin/simulate",
        json={
            "session_id": "   ",
            "scenario": "   ",
        },
    )

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["data"] is None
    assert response.json()["error"] == "Validation error"


def test_simulate_route_returns_controlled_fallback_when_service_fails() -> None:
    simulation_service = StubSimulationService(error=RuntimeError("llm failed"))
    memory_service = StubMemoryService()
    realtime_service = StubRealtimeEventService()
    app.dependency_overrides[get_simulation_service] = lambda: simulation_service
    app.dependency_overrides[get_memory_service] = lambda: memory_service
    app.dependency_overrides[get_realtime_event_service] = lambda: realtime_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/twin/simulate",
        json={
            "session_id": "session-99",
            "scenario": "Should I make the decision today?",
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "decision": "The user would pause until they can evaluate this more reliably.",
            "reasoning": "The simulation service is temporarily unavailable, so this is a controlled fallback response.",
            "debug": None,
        },
        "error": None,
    }
    assert memory_service.remember_calls[0]["metadata"]["simulation"]["is_fallback"] is True


def test_lifecycle_transition_route_returns_new_session_when_deployed() -> None:
    profile_service = StubProfileService(
        {
            "message": "Cognitive Twin deployed successfully",
            "new_session_id": "new-session-123",
            "previous_session_archived": True,
        }
    )
    app.dependency_overrides[get_profile_service] = lambda: profile_service
    client = TestClient(app)

    response = client.post("/api/v1/twin/session-1/lifecycle/transition")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "message": "Cognitive Twin deployed successfully",
            "new_session_id": "new-session-123",
            "previous_session_archived": True,
        },
        "error": None,
    }
    assert profile_service.calls == ["session-1"]


def test_lifecycle_transition_route_prevents_reset_for_training_status() -> None:
    profile_service = StubProfileService(
        {
            "message": "Cognitive Twin is still training",
            "new_session_id": None,
            "previous_session_archived": False,
        }
    )
    app.dependency_overrides[get_profile_service] = lambda: profile_service
    client = TestClient(app)

    response = client.post("/api/v1/twin/session-2/lifecycle/transition")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "message": "Cognitive Twin is still training",
            "new_session_id": None,
            "previous_session_archived": False,
        },
        "error": None,
    }
    assert profile_service.calls == ["session-2"]
