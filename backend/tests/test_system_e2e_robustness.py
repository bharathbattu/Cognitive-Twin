from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, cast

from fastapi.testclient import TestClient

from app.core.dependencies import (
    get_chat_service,
    get_memory_service,
    get_profile_service,
    get_realtime_event_service,
    get_simulation_service,
)
from app.main import app
from app.memory.retriever import Retriever
from app.services.memory.memory_service import MemoryService
from app.services.twin.chat_service import ChatService
from app.services.twin.profile_service import ProfileService
from app.services.twin.simulation_service import SimulationService

UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    flags=re.IGNORECASE,
)


class StubJsonStore:
    def __init__(self) -> None:
        self.entries: dict[str, list[dict[str, Any]]] = {}
        self.fail_load_once = False
        self.fail_append_once = False
        self.reset_calls: list[str] = []

    def append(self, session_id: str, payload: dict[str, Any]) -> None:
        if self.fail_append_once:
            self.fail_append_once = False
            raise ValueError("append failed")
        self.entries.setdefault(session_id, []).append(payload)

    def load(self, session_id: str) -> list[dict[str, Any]]:
        if self.fail_load_once:
            self.fail_load_once = False
            raise ValueError("corrupted json")
        return list(self.entries.get(session_id, []))

    def reset_session(self, session_id: str) -> None:
        self.reset_calls.append(session_id)
        self.entries[session_id] = []


class StubFaissStore:
    def __init__(self) -> None:
        self.add_calls: list[dict[str, str]] = []
        self.search_results: list[str] = []
        self.fail_add_once = False
        self.fail_search = False
        self.reset_calls: list[str] = []

    def add(self, session_id: str, memory_id: str, text: str) -> None:
        if self.fail_add_once:
            self.fail_add_once = False
            raise RuntimeError("faiss add failed")
        self.add_calls.append({"session_id": session_id, "memory_id": memory_id, "text": text})

    def search(self, session_id: str, query: str, top_k: int) -> list[str]:
        if self.fail_search:
            raise RuntimeError("faiss search failed")
        return self.search_results[:top_k]

    def reset_session(self, session_id: str) -> None:
        self.reset_calls.append(session_id)
        self.search_results = []


class StubEmbeddingManager:
    dimension = 64


class StubRealtimeEventService:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    async def publish(self, session_id: str, event_type: str, data: dict[str, Any]) -> None:
        self.events.append((session_id, event_type, data))


class StubExtractionService:
    def extract_cognition(self, text: str) -> dict[str, Any]:
        normalized = " ".join(text.strip().split())
        return {
            "thinking_style": "reflective and analytical",
            "decision_traits": ["deliberate", "tradeoff-aware"],
            "preferences": ["clear tradeoffs", "low-regret decisions"],
            "context": f"The user evaluates: {normalized}",
        }


class ScriptedOpenRouterService:
    def __init__(
        self,
        simulation_outputs: list[object] | None = None,
        chat_reply: str | None = None,
        expose_client: bool = True,
    ) -> None:
        self.simulation_outputs = list(simulation_outputs or [])
        self.chat_reply = chat_reply or "The twin response is clear and grounded in past behavior."
        self.chat_calls = 0
        self.simulation_calls = 0
        self.client = object() if expose_client else None

    async def generate_reply(self, message: str, memories: list[dict[str, Any]]) -> str:
        self.chat_calls += 1
        memory_count = len(memories)
        return f"**{self.chat_reply}** Message: {message}. Seen memories: {memory_count}."

    def call_model_sync(
        self,
        task_type: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        self.simulation_calls += 1
        if self.simulation_outputs:
            outcome = self.simulation_outputs.pop(0)
        else:
            outcome = json.dumps(
                {
                    "decision": "The user would compare options and then move with the lowest regret path.",
                    "reasoning": (
                        "The user's reflective and analytical style and tradeoff-aware trait drive a slower decision, "
                        "and in the past the user has tended to compare options before committing."
                    ),
                }
            )

        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, str):
            return outcome
        return str(outcome)


@dataclass
class SystemHarness:
    client: TestClient
    memory_service: MemoryService
    profile_service: ProfileService
    simulation_service: SimulationService
    openrouter_service: ScriptedOpenRouterService
    realtime_service: StubRealtimeEventService
    json_store: StubJsonStore
    faiss_store: StubFaissStore


def _log_pass(step: str) -> None:
    print(f"[PASS] {step}")


def _check(step: str, condition: bool, details: str = "") -> None:
    if condition:
        _log_pass(step)
        return
    suffix = f" | {details}" if details else ""
    print(f"[FAIL] {step}{suffix}")
    assert condition, f"{step}{suffix}"


def _assert_success_envelope(step: str, payload: dict[str, Any]) -> dict[str, Any]:
    _check(step + " envelope keys", set(payload.keys()) == {"success", "data", "error"}, str(payload.keys()))
    _check(step + " success flag", payload["success"] is True, str(payload))
    _check(step + " error field", payload["error"] is None, str(payload.get("error")))
    _check(step + " data field", payload["data"] is not None)
    return payload["data"]


def _build_harness(
    simulation_outputs: list[object] | None = None,
    simulation_max_retries: int = 3,
    expose_client: bool = True,
) -> SystemHarness:
    json_store = StubJsonStore()
    faiss_store = StubFaissStore()
    embedding_manager = StubEmbeddingManager()
    retriever = Retriever(
        json_store=json_store,  # type: ignore[arg-type]
        faiss_store=faiss_store,  # type: ignore[arg-type]
        embedding_manager=embedding_manager,  # type: ignore[arg-type]
    )
    memory_service = MemoryService(
        json_store=json_store,  # type: ignore[arg-type]
        faiss_store=faiss_store,  # type: ignore[arg-type]
        retriever=retriever,
        embedding_manager=embedding_manager,  # type: ignore[arg-type]
    )

    openrouter_service = ScriptedOpenRouterService(
        simulation_outputs=simulation_outputs,
        expose_client=expose_client,
    )
    realtime_service = StubRealtimeEventService()
    profile_service = ProfileService(memory_service=memory_service)
    chat_service = ChatService(
        memory_service=memory_service,
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        extraction_service=StubExtractionService(),  # type: ignore[arg-type]
        profile_service=profile_service,
        realtime_event_service=realtime_service,  # type: ignore[arg-type]
    )
    simulation_service = SimulationService(
        profile_service=profile_service,
        memory_service=memory_service,
        openrouter_service=openrouter_service,  # type: ignore[arg-type]
        max_retries=simulation_max_retries,
    )

    app.dependency_overrides[get_memory_service] = lambda: memory_service
    app.dependency_overrides[get_profile_service] = lambda: profile_service
    app.dependency_overrides[get_realtime_event_service] = lambda: realtime_service
    app.dependency_overrides[get_chat_service] = lambda: chat_service
    app.dependency_overrides[get_simulation_service] = lambda: simulation_service

    return SystemHarness(
        client=TestClient(app),
        memory_service=memory_service,
        profile_service=profile_service,
        simulation_service=simulation_service,
        openrouter_service=openrouter_service,
        realtime_service=realtime_service,
        json_store=json_store,
        faiss_store=faiss_store,
    )


def _teardown_harness() -> None:
    app.dependency_overrides.clear()


def test_core_user_flow_transition_simulation_and_output_quality() -> None:
    harness = _build_harness()
    session_id = "e2e-core-flow"

    try:
        chat_response = harness.client.post(
            "/api/v1/chat",
            json={
                "message": "I compare tradeoffs carefully before making decisions.",
                "session_id": session_id,
                "top_k": 5,
            },
        )
        _check("Step 1 chat status", chat_response.status_code == 200, str(chat_response.text))
        chat_data = _assert_success_envelope("Step 1 chat", chat_response.json())
        _check("Step 1 chat session propagation", chat_data["session_id"] == session_id)
        _check("Step 1 chat markdown cleaned", "**" not in chat_data["reply"], chat_data["reply"])

        memory_response = harness.client.get(f"/api/v1/memory/{session_id}")
        _check("Step 1 memory status", memory_response.status_code == 200, str(memory_response.text))
        memory_data = _assert_success_envelope("Step 1 memory", memory_response.json())
        roles = {item["role"] for item in memory_data["items"]}
        _check("Step 1 user input stored", "user" in roles)
        _check("Step 1 extraction stored", "cognitive_extraction" in roles)
        _check("Step 1 profile stored", "cognitive_profile" in roles)

        profile_response = harness.client.get(f"/api/v1/twin/{session_id}/profile")
        _check("Step 1 profile status", profile_response.status_code == 200, str(profile_response.text))
        profile_data = _assert_success_envelope("Step 1 profile", profile_response.json())
        _check("Step 1 status training", profile_data["twin_status"] == "training", str(profile_data))

        for i in range(2, 10):
            iterative_chat = harness.client.post(
                "/api/v1/chat",
                json={
                    "message": f"Message {i}: I review options and select the lowest-regret path.",
                    "session_id": session_id,
                    "top_k": 5,
                },
            )
            _check(f"Step 2 chat {i} status", iterative_chat.status_code == 200)

        profile_after_training = harness.client.get(f"/api/v1/twin/{session_id}/profile")
        profile_after_data = _assert_success_envelope("Step 2 profile", profile_after_training.json())
        _check(
            "Step 2 twin transitioned to deployed",
            profile_after_data["twin_status"] == "deployed",
            str(profile_after_data),
        )

        simulate_response = harness.client.post(
            "/api/v1/twin/simulate",
            json={
                "session_id": session_id,
                "scenario": "Should I launch this week or wait one week to reduce execution risk?",
                "debug": True,
            },
        )
        _check("Step 3 simulation status", simulate_response.status_code == 200, str(simulate_response.text))
        simulation_data = _assert_success_envelope("Step 3 simulation", simulate_response.json())

        decision = simulation_data["decision"]
        reasoning = simulation_data["reasoning"]
        debug_payload = cast(dict[str, Any], simulation_data.get("debug") or {})

        _check("Step 3 decision not generic", "it depends" not in decision.lower(), decision)
        _check("Step 3 reasoning references profile", "reflective and analytical" in reasoning.lower(), reasoning)
        _check("Step 3 reasoning references memory behavior", "in the past" in reasoning.lower(), reasoning)
        _check("Step 3 no markdown leakage", "**" not in f"{decision} {reasoning}")
        _check("Step 3 no uuid leakage", UUID_PATTERN.search(f"{decision} {reasoning}") is None, reasoning)
        _check("Step 3 third-person output", " i " not in f" {decision.lower()} {reasoning.lower()} ")
        _check("Step 3 debug traits present", len(debug_payload.get("used_traits", [])) > 0, str(debug_payload))

    finally:
        _teardown_harness()


def test_frontend_backend_contract_and_session_consistency() -> None:
    harness = _build_harness()
    session_id = "e2e-session-contract"

    try:
        chat_response = harness.client.post(
            "/api/v1/chat",
            json={"message": "I prefer concise status updates.", "session_id": session_id, "top_k": 5},
        )
        chat_data = _assert_success_envelope("Contract chat", chat_response.json())
        _check("Contract chat response keys", set(chat_data.keys()) == {"session_id", "reply", "model", "memory_hits"})
        _check("Contract chat session consistency", chat_data["session_id"] == session_id)

        add_memory = harness.client.post(
            f"/api/v1/memory/{session_id}",
            json={"text": "Manual memory item", "metadata": {"source": "e2e"}},
        )
        add_memory_data = _assert_success_envelope("Contract memory post", add_memory.json())
        _check("Contract memory response keys", set(add_memory_data.keys()) == {"session_id", "count", "items"})
        _check("Contract memory session consistency", add_memory_data["session_id"] == session_id)

        list_memory = harness.client.get(f"/api/v1/memory/{session_id}")
        list_memory_data = _assert_success_envelope("Contract memory get", list_memory.json())
        _check("Contract memory get session consistency", list_memory_data["session_id"] == session_id)

        profile_response = harness.client.get(f"/api/v1/twin/{session_id}/profile")
        profile_data = _assert_success_envelope("Contract profile", profile_response.json())
        _check(
            "Contract profile response keys",
            set(profile_data.keys()) == {"session_id", "summary", "memory_count", "latest_topics", "twin_status"},
        )
        _check("Contract profile session consistency", profile_data["session_id"] == session_id)

        simulation_response = harness.client.post(
            "/api/v1/twin/simulate",
            json={
                "session_id": session_id,
                "scenario": "Should I publish now or review once more?",
                "debug": False,
            },
        )
        simulation_data = _assert_success_envelope("Contract simulation", simulation_response.json())
        _check("Contract simulation keys", {"decision", "reasoning", "debug"}.issubset(set(simulation_data.keys())))

    finally:
        _teardown_harness()


def test_memory_integrity_duplicate_json_recovery_and_faiss_relevance() -> None:
    harness = _build_harness()
    session_id = "e2e-memory-integrity"

    try:
        first = cast(Any, harness.memory_service).remember_experience(
            session_id=session_id,
            text="I revisit tradeoffs before major launches.",
            metadata={"context": "release planning"},
        )
        duplicate = cast(Any, harness.memory_service).remember_experience(
            session_id=session_id,
            text="I revisit tradeoffs before major launches.",
            metadata={"context": "release planning"},
        )
        _check("Memory integrity duplicate blocked", first.id == duplicate.id)

        harness.json_store.fail_load_once = True
        recovered = cast(Any, harness.memory_service).remember(session_id=session_id, text="Recovered after JSON corruption.")
        _check("Memory integrity json recovery entry kept", recovered.text == "Recovered after JSON corruption.")
        _check("Memory integrity json recovery reset called", session_id in harness.json_store.reset_calls)

        user_a = cast(Any, harness.memory_service).remember_experience(session_id, "I delay when risks are unclear.")
        assistant = cast(Any, harness.memory_service).remember(
            session_id,
            "You should delay.",
            metadata={"semantic_memory": False},
            role="assistant",
        )
        user_b = cast(Any, harness.memory_service).remember_experience(session_id, "I compare options before committing.")

        harness.faiss_store.search_results = [user_b.id, assistant.id, user_a.id]
        retrieved = cast(
            list[dict[str, Any]],
            cast(Any, harness.memory_service).retrieve_relevant_experiences(
                session_id=session_id,
                query="How does the user handle risk?",
                top_k=2,
            ),
        )

        _check("Memory integrity retrieval count", len(retrieved) == 2, str(retrieved))
        _check("Memory integrity retrieval excludes assistant", all(item["role"] == "user" for item in retrieved))
        _check("Memory integrity retrieval ranking", [item["relevance_rank"] for item in retrieved] == [1, 2])

    finally:
        _teardown_harness()


def test_ai_failure_timeout_invalid_json_and_empty_response() -> None:
    timeout_then_success = _build_harness(
        simulation_outputs=[
            TimeoutError("openrouter timeout"),
            json.dumps(
                {
                    "decision": "The user would delay one day and verify assumptions.",
                    "reasoning": (
                        "The user's reflective and analytical style favors caution, and in the past "
                        "the user has tended to validate assumptions before final decisions."
                    ),
                }
            ),
        ],
        simulation_max_retries=3,
    )

    try:
        timeout_response = timeout_then_success.client.post(
            "/api/v1/twin/simulate",
            json={"session_id": "e2e-ai-timeout", "scenario": "Should I ship now?", "debug": False},
        )
        timeout_data = _assert_success_envelope("AI timeout retry", timeout_response.json())
        _check("AI timeout retry call count", timeout_then_success.openrouter_service.simulation_calls == 2)
        _check("AI timeout retry decision present", bool(timeout_data["decision"].strip()))
    finally:
        _teardown_harness()

    invalid_json_all_retries = _build_harness(
        simulation_outputs=["not-json", "still not json", ""],
        simulation_max_retries=3,
    )

    try:
        invalid_response = invalid_json_all_retries.client.post(
            "/api/v1/twin/simulate",
            json={"session_id": "e2e-ai-invalid", "scenario": "Should I pivot now?", "debug": False},
        )
        invalid_data = _assert_success_envelope("AI invalid-json fallback", invalid_response.json())
        _check("AI invalid-json retries exhausted", invalid_json_all_retries.openrouter_service.simulation_calls == 3)
        _check("AI invalid-json fallback decision", bool(invalid_data["decision"].strip()))
        _check("AI invalid-json fallback reasoning", bool(invalid_data["reasoning"].strip()))
    finally:
        _teardown_harness()

    empty_response_all_retries = _build_harness(
        simulation_outputs=["", "", ""],
        simulation_max_retries=3,
    )

    try:
        empty_response = empty_response_all_retries.client.post(
            "/api/v1/twin/simulate",
            json={"session_id": "e2e-ai-empty", "scenario": "Should I hire now?", "debug": False},
        )
        empty_data = _assert_success_envelope("AI empty-response fallback", empty_response.json())
        _check("AI empty-response retries exhausted", empty_response_all_retries.openrouter_service.simulation_calls == 3)
        _check("AI empty-response no crash", bool(empty_data["decision"].strip()) and bool(empty_data["reasoning"].strip()))
    finally:
        _teardown_harness()


def test_input_edge_cases_and_multi_user_lifecycle_reset() -> None:
    harness = _build_harness()

    try:
        empty_chat = harness.client.post(
            "/api/v1/chat",
            json={"message": "", "session_id": "edge-empty", "top_k": 5},
        )
        _check("Edge empty input validation", empty_chat.status_code == 422)

        whitespace_chat = harness.client.post(
            "/api/v1/chat",
            json={"message": "   ", "session_id": "edge-whitespace", "top_k": 5},
        )
        _check("Edge whitespace input validation", whitespace_chat.status_code == 422)

        whitespace_memory = harness.client.post(
            "/api/v1/memory/edge-whitespace",
            json={"text": "    ", "metadata": {}},
        )
        _check("Edge whitespace memory validation", whitespace_memory.status_code == 422)

        long_scenario = "x " * 6000
        long_response = harness.client.post(
            "/api/v1/twin/simulate",
            json={"session_id": "edge-long", "scenario": long_scenario, "debug": False},
        )
        long_data = _assert_success_envelope("Edge very long input", long_response.json())
        _check("Edge very long input no crash", bool(long_data["decision"].strip()))

        nonsense_response = harness.client.post(
            "/api/v1/twin/simulate",
            json={"session_id": "edge-nonsense", "scenario": "xqzptlkm", "debug": False},
        )
        nonsense_data = _assert_success_envelope("Edge nonsense input", nonsense_response.json())
        _check("Edge nonsense fallback", "clearer" in nonsense_data["decision"].lower(), nonsense_data["decision"])

        lifecycle_session = "edge-lifecycle"
        for i in range(9):
            response = harness.client.post(
                "/api/v1/chat",
                json={
                    "message": f"Lifecycle sample {i}: I compare options and pick the safer path.",
                    "session_id": lifecycle_session,
                    "top_k": 5,
                },
            )
            _check(f"Lifecycle chat {i} status", response.status_code == 200)

        transition = harness.client.post(f"/api/v1/twin/{lifecycle_session}/lifecycle/transition")
        transition_data = _assert_success_envelope("Multi-user lifecycle transition", transition.json())
        new_session_id = transition_data["new_session_id"]

        _check("Multi-user archive success", transition_data["previous_session_archived"] is True)
        _check("Multi-user new session issued", isinstance(new_session_id, str) and bool(new_session_id))

        new_profile = harness.client.get(f"/api/v1/twin/{new_session_id}/profile")
        new_profile_data = _assert_success_envelope("Multi-user new session profile", new_profile.json())
        _check("Multi-user clean start training", new_profile_data["twin_status"] == "training", str(new_profile_data))

    finally:
        _teardown_harness()


def test_session_mismatch_isolation_prevents_cross_session_leakage() -> None:
    harness = _build_harness()
    session_a = "e2e-mismatch-a"
    session_b = "e2e-mismatch-b"

    try:
        chat_a = harness.client.post(
            "/api/v1/chat",
            json={
                "message": "Session A marker: I prefer conservative rollout plans.",
                "session_id": session_a,
                "top_k": 5,
            },
        )
        _check("Mismatch session A chat status", chat_a.status_code == 200, str(chat_a.text))

        memory_b = harness.client.get(f"/api/v1/memory/{session_b}")
        memory_b_data = _assert_success_envelope("Mismatch memory session B", memory_b.json())
        _check("Mismatch memory session B starts empty", memory_b_data["count"] == 0, str(memory_b_data))

        profile_b = harness.client.get(f"/api/v1/twin/{session_b}/profile")
        profile_b_data = _assert_success_envelope("Mismatch profile session B", profile_b.json())
        _check("Mismatch profile session B has no memory", profile_b_data["memory_count"] == 0, str(profile_b_data))
        _check("Mismatch profile session B status training", profile_b_data["twin_status"] == "training")

        simulate_b = harness.client.post(
            "/api/v1/twin/simulate",
            json={
                "session_id": session_b,
                "scenario": "Should I launch this week or wait for more certainty?",
                "debug": True,
            },
        )
        _check("Mismatch simulation session B status", simulate_b.status_code == 200, str(simulate_b.text))
        simulation_b_data = _assert_success_envelope("Mismatch simulation session B", simulate_b.json())
        debug_payload = cast(dict[str, Any], simulation_b_data.get("debug") or {})

        _check(
            "Mismatch simulation session B used memories empty",
            len(debug_payload.get("used_memories", [])) == 0,
            str(debug_payload),
        )
    finally:
        _teardown_harness()
