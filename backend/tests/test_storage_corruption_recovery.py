from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.memory.embedding_manager import EmbeddingManager
from app.memory.faiss_store import FaissStore, faiss
from app.memory.json_store import JsonStore
from app.utils.file_helpers import safe_slug


def test_json_store_resets_corrupted_json_file_on_disk(tmp_path: Path) -> None:
    store = JsonStore()
    store.base_path = tmp_path

    session_id = "corrupt/session"
    payload_path = tmp_path / f"{safe_slug(session_id)}.json"
    payload_path.write_text("{not-valid-json", encoding="utf-8")

    loaded = store.load(session_id)

    assert loaded == []
    assert payload_path.read_text(encoding="utf-8") == "[]"


def test_json_store_resets_non_list_payload_on_disk(tmp_path: Path) -> None:
    store = JsonStore()
    store.base_path = tmp_path

    session_id = "corrupt/non-list"
    payload_path = tmp_path / f"{safe_slug(session_id)}.json"
    payload_path.write_text(json.dumps({"unexpected": True}), encoding="utf-8")

    loaded = store.load(session_id)

    assert loaded == []
    assert payload_path.read_text(encoding="utf-8") == "[]"


def test_faiss_store_resets_corrupted_state_on_disk(tmp_path: Path) -> None:
    store = FaissStore(embedding_manager=EmbeddingManager())
    store.base_path = tmp_path

    session_id = "corrupt-faiss"
    ids_path = tmp_path / f"{safe_slug(session_id)}.ids"
    ids_path.write_text("memory-1\n", encoding="utf-8")

    index_path = tmp_path / f"{safe_slug(session_id)}.index"
    vectors_path = tmp_path / f"{safe_slug(session_id)}.npy"

    if faiss is not None:
        index_path.write_text("corrupted index payload", encoding="utf-8")
    else:
        np.save(vectors_path, np.array([1.0, 2.0, 3.0], dtype=np.float32))

    memory_ids = store.search(session_id=session_id, query="How does the user handle risk?", top_k=3)

    assert memory_ids == []
    assert not ids_path.exists()
    if faiss is not None:
        assert not index_path.exists()
    else:
        assert not vectors_path.exists()
