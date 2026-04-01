import json
import logging
import re
from typing import Any

from app.models.schemas.chat import ChatRequest, ChatResponse
from app.services.ai.openrouter_service import OpenRouterService
from app.services.memory.memory_service import MemoryService
from app.services.twin.extraction_service import ExtractionService
from app.services.twin.profile_service import ProfileService
from app.services.twin.realtime_service import RealtimeEventService

logger = logging.getLogger(__name__)

COGNITIVE_EXTRACTION_ROLE = "cognitive_extraction"


def clean_response(text: str) -> str:
    if not text:
        return text

    # Remove bold markdown markers (**text** -> text).
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)

    # Remove any remaining star characters.
    text = re.sub(r"\*", "", text)

    # Remove numbered list formatting (1. , 2. , etc.).
    text = re.sub(r"\d+\.\s*", "", text)

    # Normalize whitespace to a single-space conversational string.
    text = re.sub(r"\s+", " ", text).strip()

    return text


class ChatService:
    def __init__(
        self,
        memory_service: MemoryService,
        openrouter_service: OpenRouterService,
        extraction_service: ExtractionService,
        profile_service: ProfileService,
        realtime_event_service: RealtimeEventService,
    ) -> None:
        self.memory_service = memory_service
        self.openrouter_service = openrouter_service
        self.extraction_service = extraction_service
        self.profile_service = profile_service
        self.realtime_event_service = realtime_event_service

    async def chat(self, payload: ChatRequest) -> ChatResponse:
        memory_hits = self.memory_service.recall(
            session_id=payload.session_id,
            query=payload.message,
            top_k=payload.top_k,
        )

        profile_data = self._extract_and_store_cognition(payload.session_id, payload.message)
        raw_response = await self.openrouter_service.generate_reply(payload.message, memory_hits)
        cleaned_response = clean_response(raw_response)
        logger.debug("Chat raw response session='%s': %s", payload.session_id, raw_response)

        self.memory_service.remember(
            session_id=payload.session_id,
            text=payload.message,
            metadata={"source": "user"},
            role="user",
        )
        self.memory_service.remember(
            session_id=payload.session_id,
            text=cleaned_response,
            metadata={"source": "assistant"},
            role="assistant",
        )

        # Emit after persistence to guarantee write-confirmed state propagation.
        await self.realtime_event_service.publish(
            session_id=payload.session_id,
            event_type="memory_update",
            data=self.memory_service.list_memories(payload.session_id).model_dump(mode="json"),
        )
        if profile_data:
            await self.realtime_event_service.publish(
                session_id=payload.session_id,
                event_type="profile_update",
                data=self.profile_service.build_profile(payload.session_id).model_dump(mode="json"),
            )

        return ChatResponse(
            session_id=payload.session_id,
            reply=cleaned_response,
            model="openrouter",
            memory_hits=memory_hits,
        )

    def _extract_and_store_cognition(self, session_id: str, message: str) -> dict[str, Any]:
        try:
            extraction = self.extraction_service.extract_cognition(message)
            logger.info("Extracted cognitive output for session '%s': %s", session_id, extraction)
            self.memory_service.remember(
                session_id=session_id,
                text=json.dumps(extraction, ensure_ascii=True),
                metadata={"source": "extraction_engine", "extraction": extraction},
                role=COGNITIVE_EXTRACTION_ROLE,
            )
            profile_payload = self.profile_service.update_profile(session_id, extraction)
            logger.info("Updated cognitive profile for session '%s': %s", session_id, profile_payload)
            return profile_payload
        except Exception:
            logger.exception("Cognitive extraction pipeline failed for session '%s'", session_id)
            return {
                "thinking_style": "unknown",
                "decision_traits": [],
                "preferences": [],
                "context": "The cognitive extraction pipeline failed for this message.",
            }
