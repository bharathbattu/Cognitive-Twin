from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any
from uuid import uuid4

from app.memory.embedding_manager import EmbeddingManager
from app.memory.faiss_store import FaissStore
from app.memory.json_store import JsonStore
from app.memory.retriever import Retriever
from app.models.domain.memory_entry import MemoryEntry
from app.models.schemas.memory import MemoryItem, MemoryListResponse

SEMANTIC_EXPERIENCE_ROLE = "user"
COGNITIVE_PROFILE_ROLE = "cognitive_profile"
logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(
        self,
        json_store: JsonStore,
        faiss_store: FaissStore,
        retriever: Retriever,
        embedding_manager: EmbeddingManager,
    ) -> None:
        self.json_store = json_store
        self.faiss_store = faiss_store
        self.retriever = retriever
        self.embedding_manager = embedding_manager

    def remember(self, session_id: str, text: str, metadata: dict | None = None, role: str = "memory") -> MemoryEntry:
        entry_metadata = dict(metadata or {})
        logger.info(
            "Memory remember requested for session='%s' role='%s' text_chars=%s",
            session_id,
            role,
            len(text),
        )
        if role == SEMANTIC_EXPERIENCE_ROLE:
            entry_metadata.setdefault("memory_kind", "experience")
            entry_metadata.setdefault("semantic_memory", True)
            entry_metadata.setdefault("phase", self._resolve_memory_phase(session_id))

        existing_entries = self._safe_get_entries(session_id)
        duplicate_entry = self._find_duplicate_entry(
            entries=existing_entries,
            text=text,
            role=role,
            metadata=entry_metadata,
        )
        if duplicate_entry is not None:
            logger.info(
                "Skipping duplicate memory entry for session '%s' role='%s'.",
                session_id,
                role,
            )
            return duplicate_entry

        entry = MemoryEntry(
            id=str(uuid4()),
            session_id=session_id,
            text=text,
            role=role,
            metadata=entry_metadata,
            created_at=datetime.now(UTC),
        )
        payload = entry.model_dump(mode="json")
        self._append_memory(session_id, payload)

        if self._should_index_memory(role=role, metadata=entry_metadata):
            self._index_memory(
                session_id=session_id,
                memory_id=entry.id,
                text=self._build_semantic_text(text=entry.text, metadata=entry_metadata),
            )
        logger.info(
            "Memory remember completed for session='%s' role='%s' id='%s'",
            session_id,
            role,
            entry.id,
        )
        return entry

    def remember_experience(self, session_id: str, text: str, metadata: dict | None = None) -> MemoryEntry:
        return self.remember(session_id=session_id, text=text, metadata=metadata, role=SEMANTIC_EXPERIENCE_ROLE)

    def retrieve_relevant_experiences(self, session_id: str, query: str, top_k: int = 5) -> list[dict]:
        try:
            results = self.retriever.search(
                session_id=session_id,
                query=query,
                top_k=top_k,
                roles={SEMANTIC_EXPERIENCE_ROLE},
                metadata_filters={"semantic_memory": True},
            )
            logger.info(
                "Memory recall completed for session='%s' query_chars=%s results=%s",
                session_id,
                len(query),
                len(results),
            )
            return results
        except Exception:
            logger.exception(
                "Memory retrieval failed for session '%s'. Resetting semantic index and returning no matches.",
                session_id,
            )
            self._reset_session_storage(self.faiss_store, session_id=session_id)
            return []

    def recall(self, session_id: str, query: str, top_k: int = 5) -> list[dict]:
        return self.retrieve_relevant_experiences(session_id=session_id, query=query, top_k=top_k)

    def get_memories(
        self,
        session_id: str,
        role: str | None = None,
        metadata_key: str | None = None,
    ) -> list[MemoryEntry]:
        entries = self._safe_get_entries(session_id)
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
        items = [MemoryItem.model_validate(item.model_dump(mode="json")) for item in self.get_memories(session_id)]
        logger.info("Memory list requested for session='%s' count=%s", session_id, len(items))
        return MemoryListResponse(session_id=session_id, count=len(items), items=items)

    def reset_session(self, session_id: str) -> None:
        logger.info("Resetting memory session state for session='%s'", session_id)
        self._reset_session_storage(self.json_store, session_id=session_id)
        self._reset_session_storage(self.faiss_store, session_id=session_id)

    def _should_index_memory(self, role: str, metadata: dict[str, Any]) -> bool:
        if "semantic_memory" in metadata:
            return bool(metadata["semantic_memory"])
        return role in {SEMANTIC_EXPERIENCE_ROLE, "memory"}

    def _build_semantic_text(self, text: str, metadata: dict[str, Any]) -> str:
        context = metadata.get("context")
        tags = metadata.get("tags")

        semantic_chunks = [text.strip()]
        if isinstance(context, str) and context.strip():
            semantic_chunks.append(context.strip())
        if isinstance(tags, list):
            tag_text = ", ".join(tag for tag in tags if isinstance(tag, str) and tag.strip())
            if tag_text:
                semantic_chunks.append(tag_text)

        return " | ".join(chunk for chunk in semantic_chunks if chunk)

    def _safe_get_entries(self, session_id: str) -> list[MemoryEntry]:
        try:
            payload = self.json_store.load(session_id)
            return [MemoryEntry.model_validate(item) for item in payload]
        except Exception:
            logger.exception(
                "Memory JSON state was unreadable for session '%s'. Resetting session memory store.",
                session_id,
            )
            self._reset_session_storage(self.json_store, session_id=session_id)
            return []

    def _append_memory(self, session_id: str, payload: dict[str, Any]) -> None:
        try:
            self.json_store.append(session_id, payload)
        except Exception:
            logger.exception(
                "Memory append failed for session '%s'. Resetting session memory store and retrying once.",
                session_id,
            )
            self._reset_session_storage(self.json_store, session_id=session_id)
            self.json_store.append(session_id, payload)

    def _index_memory(self, session_id: str, memory_id: str, text: str) -> None:
        try:
            self.faiss_store.add(session_id=session_id, memory_id=memory_id, text=text)
        except Exception:
            logger.exception(
                "Semantic index update failed for session '%s'. Resetting index and retrying once.",
                session_id,
            )
            self._reset_session_storage(self.faiss_store, session_id=session_id)
            try:
                self.faiss_store.add(session_id=session_id, memory_id=memory_id, text=text)
            except Exception:
                logger.exception(
                    "Semantic index recovery failed for session '%s'. Continuing without semantic index update.",
                    session_id,
                )

    def _find_duplicate_entry(
        self,
        entries: list[MemoryEntry],
        text: str,
        role: str,
        metadata: dict[str, Any],
    ) -> MemoryEntry | None:
        normalized_text = " ".join(text.strip().split())
        for entry in reversed(entries):
            if entry.role != role:
                continue
            if " ".join(entry.text.strip().split()) != normalized_text:
                continue
            if entry.metadata != metadata:
                continue
            return entry
        return None

    def _reset_session_storage(self, store: Any, session_id: str) -> None:
        reset_session = getattr(store, "reset_session", None)
        if callable(reset_session):
            reset_session(session_id)

    def _resolve_memory_phase(self, session_id: str) -> str:
        latest_profile = self.latest_memory(
            session_id=session_id,
            role=COGNITIVE_PROFILE_ROLE,
            metadata_key="twin_status",
        )
        if latest_profile and latest_profile.metadata.get("twin_status") == "deployed":
            return "post-deployment"
        return "training"
