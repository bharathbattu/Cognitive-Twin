from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.utils.file_helpers import ensure_directory, safe_slug

logger = logging.getLogger(__name__)


class JsonStore:
    def __init__(self) -> None:
        self.base_path = get_settings().resolved_memory_json_path
        ensure_directory(self.base_path)

    def append(self, session_id: str, payload: dict[str, Any]) -> None:
        entries = self.load(session_id)
        entries.append(payload)
        self._path(session_id).write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def load(self, session_id: str) -> list[dict[str, Any]]:
        path = self._path(session_id)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            logger.exception("Memory JSON file was corrupted for session '%s'. Resetting it.", session_id)
            self.reset_session(session_id)
            return []

        if not isinstance(payload, list):
            logger.warning("Memory JSON payload was not a list for session '%s'. Resetting it.", session_id)
            self.reset_session(session_id)
            return []
        return payload

    def reset_session(self, session_id: str) -> None:
        self._path(session_id).write_text("[]", encoding="utf-8")

    def _path(self, session_id: str) -> Path:
        return self.base_path / f"{safe_slug(session_id)}.json"
