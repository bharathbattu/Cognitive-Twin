from __future__ import annotations

from typing import Any

from app.memory.embedding_manager import EmbeddingManager
from app.memory.faiss_store import FaissStore
from app.memory.json_store import JsonStore


class Retriever:
    def __init__(
        self,
        json_store: JsonStore,
        faiss_store: FaissStore,
        embedding_manager: EmbeddingManager,
    ) -> None:
        self.json_store = json_store
        self.faiss_store = faiss_store
        self.embedding_manager = embedding_manager

    def search(
        self,
        session_id: str,
        query: str,
        top_k: int,
        roles: set[str] | None = None,
        metadata_filters: dict[str, Any] | None = None,
    ) -> list[dict]:
        memories = self.json_store.load(session_id)
        if not memories:
            return []

        by_id = {memory["id"]: memory for memory in memories}
        candidate_count = min(max(top_k * 4, top_k), len(by_id))
        matches = self.faiss_store.search(session_id=session_id, query=query, top_k=candidate_count)

        relevant_memories: list[dict[str, Any]] = []
        for memory_id in matches:
            memory = by_id.get(memory_id)
            if memory is None:
                continue
            if roles is not None and memory.get("role") not in roles:
                continue
            if not self._matches_metadata(memory, metadata_filters):
                continue

            relevant_memories.append(
                {
                    **memory,
                    "relevance_rank": len(relevant_memories) + 1,
                }
            )
            if len(relevant_memories) == top_k:
                break

        return relevant_memories

    def _matches_metadata(self, memory: dict[str, Any], metadata_filters: dict[str, Any] | None) -> bool:
        if metadata_filters is None:
            return True

        memory_metadata = memory.get("metadata", {})
        if not isinstance(memory_metadata, dict):
            return False

        for key, expected in metadata_filters.items():
            if memory_metadata.get(key) != expected:
                return False
        return True
