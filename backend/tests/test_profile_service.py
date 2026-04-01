from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.models.domain.memory_entry import MemoryEntry
from app.models.schemas.memory import MemoryItem, MemoryListResponse
from app.services.twin.profile_service import COGNITIVE_PROFILE_ROLE, MIN_OBSERVATIONS, ProfileService


class StubMemoryService:
    def __init__(self) -> None:
        self.records: list[MemoryEntry] = []

    def reset_session(self, session_id: str) -> None:
        self.records = [entry for entry in self.records if entry.session_id != session_id]

    def remember(self, session_id: str, text: str, metadata: dict | None = None, role: str = "memory") -> MemoryEntry:
        entry = MemoryEntry(
            id=str(uuid4()),
            session_id=session_id,
            text=text,
            role=role,
            metadata=metadata or {},
            created_at=datetime.now(UTC),
        )
        self.records.append(entry)
        return entry

    def get_memories(
        self,
        session_id: str,
        role: str | None = None,
        metadata_key: str | None = None,
    ) -> list[MemoryEntry]:
        entries = [entry for entry in self.records if entry.session_id == session_id]
        if role is not None:
            entries = [entry for entry in entries if entry.role == role]
        if metadata_key is not None:
            entries = [entry for entry in entries if metadata_key in entry.metadata]
        return entries

    def latest_memory(
        self,
        session_id: str,
        role: str,
        metadata_key: str | None = None,
    ) -> MemoryEntry | None:
        entries = self.get_memories(session_id=session_id, role=role, metadata_key=metadata_key)
        return entries[-1] if entries else None

    def list_memories(self, session_id: str) -> MemoryListResponse:
        entries = [entry for entry in self.records if entry.session_id == session_id]
        items = [MemoryItem.model_validate(entry.model_dump(mode="json")) for entry in entries]
        return MemoryListResponse(session_id=session_id, count=len(items), items=items)


def test_profile_service_merges_traits_and_tracks_frequency() -> None:
    memory_service = StubMemoryService()
    service = ProfileService(memory_service=memory_service)  # type: ignore[arg-type]

    service.update_profile(
        "session-1",
        {
            "thinking_style": "Reflective and analytical",
            "decision_traits": ["deliberate", "tradeoff-aware"],
            "preferences": ["clear tradeoffs"],
            "context": "Decision process",
        },
    )
    profile = service.update_profile(
        "session-1",
        {
            "thinking_style": "reflective and analytical",
            "decision_traits": ["deliberate", "evidence-seeking"],
            "preferences": ["clear tradeoffs", "low-clutter interfaces"],
            "context": "Information consumption",
        },
    )

    assert profile["thinking_style"] == ["reflective and analytical"]
    assert profile["decision_traits"] == ["deliberate", "tradeoff-aware", "evidence-seeking"]
    assert profile["preferences"] == ["clear tradeoffs", "low-clutter interfaces"]
    assert profile["contexts"] == ["decision process", "information consumption"]

    stored_profile = service.get_profile("session-1")
    assert stored_profile == profile

    latest_snapshot = memory_service.latest_memory("session-1", COGNITIVE_PROFILE_ROLE, metadata_key="weights")
    assert latest_snapshot is not None
    weights = latest_snapshot.metadata["weights"]
    assert weights["thinking_style"]["reflective and analytical"] == 2
    assert weights["decision_traits"]["deliberate"] == 2
    assert weights["preferences"]["clear tradeoffs"] == 2


def test_profile_service_formats_recent_contexts_as_clean_bullets() -> None:
    memory_service = StubMemoryService()
    service = ProfileService(memory_service=memory_service)  # type: ignore[arg-type]

    service.update_profile(
        "session-2",
        {
            "thinking_style": "Reflective and analytical",
            "decision_traits": ["deliberate"],
            "preferences": ["clear tradeoffs"],
            "context": "the user expresses a preference for clear tradeoffs",
        },
    )
    service.update_profile(
        "session-2",
        {
            "thinking_style": "Reflective and analytical",
            "decision_traits": ["tradeoff-aware"],
            "preferences": ["independence"],
            "context": "the user expresses a preference for clear tradeoffs in launches",
        },
    )
    service.update_profile(
        "session-2",
        {
            "thinking_style": "Reflective and analytical",
            "decision_traits": ["balanced"],
            "preferences": ["financial stability"],
            "context": "they balance growth with financial stability",
        },
    )
    service.update_profile(
        "session-2",
        {
            "thinking_style": "Reflective and analytical",
            "decision_traits": ["independent"],
            "preferences": ["control"],
            "context": "the user values independence and control",
        },
    )

    summary = service.build_profile("session-2").summary

    assert "Dominant thinking style: reflective and analytical" in summary
    assert "Decision traits:" in summary
    assert "Preferences:" in summary
    assert "Recent contexts:" in summary
    assert "- Prefers clear tradeoffs." in summary
    assert "- Balances growth with financial stability." in summary
    assert "- Values independence and control." in summary
    assert "the user expresses" not in summary
    assert "Prefers clear tradeoffs in launches." not in summary


def test_profile_status_stays_training_below_threshold() -> None:
    memory_service = StubMemoryService()
    service = ProfileService(memory_service=memory_service)  # type: ignore[arg-type]

    for index in range(3):
        memory_service.remember(
            session_id="session-training",
            text=f"User input number {index} about tradeoffs and planning.",
            role="user",
        )

    service.update_profile(
        "session-training",
        {
            "thinking_style": "Reflective",
            "decision_traits": ["deliberate"],
            "preferences": ["clear tradeoffs"],
            "context": "weekly planning",
        },
    )

    profile_response = service.build_profile("session-training")
    assert profile_response.twin_status == "training"


def test_profile_status_becomes_deployed_after_threshold() -> None:
    memory_service = StubMemoryService()
    service = ProfileService(memory_service=memory_service)  # type: ignore[arg-type]

    for index in range(MIN_OBSERVATIONS):
        memory_service.remember(
            session_id="session-deployed",
            text=f"Observation {index} includes meaningful user preferences and decisions.",
            role="user",
        )

    service.update_profile(
        "session-deployed",
        {
            "thinking_style": "Reflective",
            "decision_traits": ["deliberate"],
            "preferences": ["clear tradeoffs"],
            "context": "release planning",
        },
    )

    profile_response = service.build_profile("session-deployed")
    assert profile_response.twin_status == "deployed"


def test_lifecycle_transition_archives_and_initializes_new_session() -> None:
    memory_service = StubMemoryService()

    with TemporaryDirectory() as temp_dir:
        service = ProfileService(
            memory_service=memory_service,  # type: ignore[arg-type]
            archive_path=Path(temp_dir),
        )

        for index in range(MIN_OBSERVATIONS):
            memory_service.remember(
                session_id="session-archive",
                text=f"Meaningful user input {index} with enough context to count.",
                role="user",
            )

        service.update_profile(
            "session-archive",
            {
                "thinking_style": "Reflective",
                "decision_traits": ["deliberate"],
                "preferences": ["clear tradeoffs"],
                "context": "launch planning",
            },
        )

        transition = service.transition_lifecycle_if_deployed("session-archive")

        assert transition["previous_session_archived"] is True
        assert transition["message"] == "Cognitive Twin deployed successfully"
        assert isinstance(transition["new_session_id"], str)
        assert transition["new_session_id"]

        archive_files = list(Path(temp_dir).glob("*.json"))
        assert len(archive_files) == 1

        new_session = transition["new_session_id"]
        new_profile_entry = memory_service.latest_memory(new_session, COGNITIVE_PROFILE_ROLE, metadata_key="twin_status")
        assert new_profile_entry is not None
        assert new_profile_entry.metadata["twin_status"] == "training"


def test_lifecycle_transition_is_blocked_while_training() -> None:
    memory_service = StubMemoryService()
    service = ProfileService(memory_service=memory_service)  # type: ignore[arg-type]

    memory_service.remember(
        session_id="session-training-reset",
        text="Only one user input.",
        role="user",
    )

    transition = service.transition_lifecycle_if_deployed("session-training-reset")

    assert transition == {
        "message": "Cognitive Twin is still training",
        "new_session_id": None,
        "previous_session_archived": False,
    }
