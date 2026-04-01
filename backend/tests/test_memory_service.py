from __future__ import annotations

from app.memory.retriever import Retriever
from app.services.memory.memory_service import MemoryService


class StubJsonStore:
    def __init__(self) -> None:
        self.entries: dict[str, list[dict]] = {}
        self.fail_load_once = False
        self.fail_append_once = False
        self.reset_calls: list[str] = []

    def append(self, session_id: str, payload: dict) -> None:
        if self.fail_append_once:
            self.fail_append_once = False
            raise ValueError("append failed")
        self.entries.setdefault(session_id, []).append(payload)

    def load(self, session_id: str) -> list[dict]:
        if self.fail_load_once:
            self.fail_load_once = False
            raise ValueError("corrupted json")
        return list(self.entries.get(session_id, []))

    def reset_session(self, session_id: str) -> None:
        self.reset_calls.append(session_id)
        self.entries[session_id] = []


class StubFaissStore:
    def __init__(self) -> None:
        self.add_calls: list[dict] = []
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


def build_memory_service(
    json_store: StubJsonStore | None = None,
    faiss_store: StubFaissStore | None = None,
) -> tuple[MemoryService, StubJsonStore, StubFaissStore]:
    resolved_json_store = json_store or StubJsonStore()
    resolved_faiss_store = faiss_store or StubFaissStore()
    retriever = Retriever(
        json_store=resolved_json_store,  # type: ignore[arg-type]
        faiss_store=resolved_faiss_store,  # type: ignore[arg-type]
        embedding_manager=StubEmbeddingManager(),  # type: ignore[arg-type]
    )
    memory_service = MemoryService(
        json_store=resolved_json_store,  # type: ignore[arg-type]
        faiss_store=resolved_faiss_store,  # type: ignore[arg-type]
        retriever=retriever,
        embedding_manager=StubEmbeddingManager(),  # type: ignore[arg-type]
    )
    return memory_service, resolved_json_store, resolved_faiss_store


def test_remember_experience_indexes_user_input_with_semantic_metadata() -> None:
    memory_service, _json_store, faiss_store = build_memory_service()

    entry = memory_service.remember_experience(
        session_id="session-1",
        text="I prefer concise updates during uncertain situations.",
        metadata={"context": "weekly review", "tags": ["updates", "uncertainty"]},
    )

    assert entry.metadata["semantic_memory"] is True
    assert entry.metadata["memory_kind"] == "experience"
    assert entry.metadata["phase"] == "training"
    assert len(faiss_store.add_calls) == 1
    assert "weekly review" in faiss_store.add_calls[0]["text"]


def test_remember_experience_tags_post_deployment_phase_when_twin_is_deployed() -> None:
    memory_service, _json_store, _faiss_store = build_memory_service()

    memory_service.remember(
        session_id="session-phase",
        text="Profile snapshot",
        metadata={
            "profile": {"thinking_style": ["reflective"]},
            "weights": {"thinking_style": {"reflective": 8}},
            "twin_status": "deployed",
        },
        role="cognitive_profile",
    )

    entry = memory_service.remember_experience(
        session_id="session-phase",
        text="I evaluate tradeoffs before committing.",
    )

    assert entry.metadata["phase"] == "post-deployment"


def test_retrieve_relevant_experiences_returns_ranked_user_memories_only() -> None:
    memory_service, _json_store, faiss_store = build_memory_service()

    first = memory_service.remember_experience("session-2", "I slow down when tradeoffs are unclear.")
    _assistant = memory_service.remember(
        "session-2",
        "You should consider the tradeoffs carefully.",
        metadata={"semantic_memory": False},
        role="assistant",
    )
    second = memory_service.remember_experience("session-2", "I trust patterns from past launches.")

    faiss_store.search_results = [second.id, _assistant.id, first.id]

    experiences = memory_service.retrieve_relevant_experiences(
        session_id="session-2",
        query="How do I behave when evaluating tradeoffs?",
        top_k=2,
    )

    assert [experience["id"] for experience in experiences] == [second.id, first.id]
    assert [experience["relevance_rank"] for experience in experiences] == [1, 2]
    assert all(experience["role"] == "user" for experience in experiences)


def test_remember_skips_duplicate_memory_entries() -> None:
    memory_service, json_store, faiss_store = build_memory_service()

    first = memory_service.remember_experience(
        "session-3",
        "I prefer calm planning.",
        metadata={"context": "retro"},
    )
    duplicate = memory_service.remember_experience(
        "session-3",
        "I prefer calm planning.",
        metadata={"context": "retro"},
    )

    assert duplicate.id == first.id
    assert len(json_store.entries["session-3"]) == 1
    assert len(faiss_store.add_calls) == 1


def test_remember_recovers_from_corrupted_json_state() -> None:
    json_store = StubJsonStore()
    json_store.fail_load_once = True
    memory_service, resolved_json_store, _faiss_store = build_memory_service(json_store=json_store)

    entry = memory_service.remember("session-4", "Recovered memory payload.")

    assert entry.text == "Recovered memory payload."
    assert resolved_json_store.reset_calls == ["session-4"]
    assert len(resolved_json_store.entries["session-4"]) == 1


def test_remember_recovers_from_append_failure() -> None:
    json_store = StubJsonStore()
    json_store.fail_append_once = True
    memory_service, resolved_json_store, _faiss_store = build_memory_service(json_store=json_store)

    entry = memory_service.remember("session-5", "Append should recover.")

    assert entry.text == "Append should recover."
    assert resolved_json_store.reset_calls == ["session-5"]
    assert len(resolved_json_store.entries["session-5"]) == 1


def test_retrieve_relevant_experiences_returns_empty_when_index_lookup_fails() -> None:
    faiss_store = StubFaissStore()
    faiss_store.fail_search = True
    memory_service, _json_store, resolved_faiss_store = build_memory_service(faiss_store=faiss_store)

    memory_service.remember_experience("session-6", "I revisit tradeoffs before shipping.")
    experiences = memory_service.retrieve_relevant_experiences(
        session_id="session-6",
        query="How do I handle risk?",
        top_k=3,
    )

    assert experiences == []
    assert resolved_faiss_store.reset_calls == ["session-6"]


def test_remember_recovers_from_faiss_add_failure() -> None:
    faiss_store = StubFaissStore()
    faiss_store.fail_add_once = True
    memory_service, _json_store, resolved_faiss_store = build_memory_service(faiss_store=faiss_store)

    entry = memory_service.remember_experience("session-7", "I slow down when risks conflict.")

    assert entry.text == "I slow down when risks conflict."
    assert resolved_faiss_store.reset_calls == ["session-7"]
    assert len(resolved_faiss_store.add_calls) == 1
