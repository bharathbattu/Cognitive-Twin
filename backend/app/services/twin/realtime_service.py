from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, cast

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections[session_id].add(websocket)
        logger.info("WebSocket connected for session '%s'.", session_id)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self.active_connections.get(session_id)
            if not connections:
                return
            connections.discard(websocket)
            if not connections:
                self.active_connections.pop(session_id, None)
        logger.info("WebSocket disconnected for session '%s'.", session_id)

    async def send_update(self, session_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self.active_connections.get(session_id, set()))

        if not connections:
            return

        stale_connections: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(data)
            except Exception:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            await self.disconnect(session_id=session_id, websocket=websocket)


class RealtimeEventService:
    def __init__(self, manager: ConnectionManager) -> None:
        self.manager = manager

    async def publish(self, session_id: str, event_type: str, data: dict[str, Any]) -> None:
        payload: dict[str, Any] = {
            "type": event_type,
            "data": data,
        }
        await self.manager.send_update(session_id=session_id, data=payload)

    async def publish_error(self, session_id: str, message: str, details: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "message": message,
            "details": details or {},
        }
        await self.publish(session_id=session_id, event_type="error", data=payload)

    async def send_connection_ack(self, session_id: str) -> None:
        await self.publish(
            session_id=session_id,
            event_type="memory_update",
            data={
                "session_id": session_id,
                "status": "connected",
            },
        )


def parse_json_message(raw_message: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_message)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        parsed_map = cast(dict[Any, Any], parsed)
        result: dict[str, Any] = {}
        for key, value in parsed_map.items():
            result[str(key)] = value
        return result
    return {}
