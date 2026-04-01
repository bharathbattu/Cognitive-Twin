from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import numpy as np

from app.core.config import get_settings
from app.memory.embedding_manager import EmbeddingManager
from app.utils.file_helpers import ensure_directory, safe_slug

try:
    import faiss  # type: ignore
except ImportError:  # pragma: no cover
    faiss = None

logger = logging.getLogger(__name__)


class FaissStore:
    def __init__(self, embedding_manager: EmbeddingManager) -> None:
        self.embedding_manager = embedding_manager
        self.dimension = embedding_manager.dimension
        self.base_path = get_settings().resolved_memory_faiss_path
        ensure_directory(self.base_path)

    def add(self, session_id: str, memory_id: str, text: str) -> None:
        index, ids = self._load(session_id)
        vector = self.embedding_manager.embed(text).reshape(1, -1).astype("float32")
        ids.append(memory_id)

        if faiss is not None:
            faiss_index = cast(Any, index)
            faiss_index.add(vector)
            faiss.write_index(faiss_index, str(self._index_path(session_id)))
        else:
            matrix = cast(np.ndarray, index)
            stacked = np.vstack([matrix, vector]) if matrix.size else vector
            np.save(self._vectors_path(session_id), stacked)

        self._write_ids(session_id, ids)

    def search(self, session_id: str, query: str, top_k: int) -> list[str]:
        index, ids = self._load(session_id)
        if not ids:
            return []

        query_vector = self.embedding_manager.embed(query).reshape(1, -1).astype("float32")

        if faiss is not None:
            faiss_index = cast(Any, index)
            _distances, positions = faiss_index.search(query_vector, min(top_k, len(ids)))
            memory_ids: list[str] = []
            for pos in positions[0]:
                if 0 <= pos < len(ids):
                    memory_ids.append(ids[pos])
            return memory_ids

        matrix = cast(np.ndarray, index)
        scores = (matrix @ query_vector.T).reshape(-1)
        ranked_indices = np.argsort(scores)[::-1][:top_k]
        return [ids[i] for i in ranked_indices.tolist()]

    def _load(self, session_id: str) -> tuple[Any, list[str]]:
        try:
            ids = self._read_ids(session_id)

            if faiss is not None:
                index_path = self._index_path(session_id)
                if index_path.exists():
                    return faiss.read_index(str(index_path)), ids
                return faiss.IndexFlatIP(self.dimension), ids

            vectors_path = self._vectors_path(session_id)
            if vectors_path.exists():
                matrix = np.load(vectors_path)
                if matrix.ndim != 2 or matrix.shape[1] != self.dimension:
                    raise ValueError("FAISS numpy index shape was invalid.")
                return matrix, ids
            return np.empty((0, self.dimension), dtype=np.float32), ids
        except Exception:
            logger.exception("Semantic index state was corrupted for session '%s'. Resetting it.", session_id)
            self.reset_session(session_id)
            if faiss is not None:
                return faiss.IndexFlatIP(self.dimension), []
            return np.empty((0, self.dimension), dtype=np.float32), []

    def _index_path(self, session_id: str) -> Path:
        return self.base_path / f"{safe_slug(session_id)}.index"

    def _vectors_path(self, session_id: str) -> Path:
        return self.base_path / f"{safe_slug(session_id)}.npy"

    def _ids_path(self, session_id: str) -> Path:
        return self.base_path / f"{safe_slug(session_id)}.ids"

    def _read_ids(self, session_id: str) -> list[str]:
        path = self._ids_path(session_id)
        if not path.exists():
            return []
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _write_ids(self, session_id: str, ids: list[str]) -> None:
        self._ids_path(session_id).write_text("\n".join(ids), encoding="utf-8")

    def reset_session(self, session_id: str) -> None:
        for path in (self._index_path(session_id), self._vectors_path(session_id), self._ids_path(session_id)):
            if path.exists():
                path.unlink()
