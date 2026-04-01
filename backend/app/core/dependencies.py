from functools import lru_cache

from app.core.config import get_settings
from app.memory.embedding_manager import EmbeddingManager
from app.memory.faiss_store import FaissStore
from app.memory.json_store import JsonStore
from app.memory.retriever import Retriever
from app.services.ai.openrouter_service import OpenRouterService
from app.services.memory.memory_service import MemoryService
from app.services.twin.chat_service import ChatService
from app.services.twin.extraction_service import ExtractionService
from app.services.twin.profile_service import ProfileService
from app.services.twin.realtime_service import ConnectionManager, RealtimeEventService
from app.services.twin.simulation_service import SimulationService


@lru_cache
def get_memory_service() -> MemoryService:
    embedding_manager = EmbeddingManager()
    json_store = JsonStore()
    faiss_store = FaissStore(embedding_manager=embedding_manager)
    retriever = Retriever(json_store=json_store, faiss_store=faiss_store, embedding_manager=embedding_manager)
    return MemoryService(
        json_store=json_store,
        faiss_store=faiss_store,
        retriever=retriever,
        embedding_manager=embedding_manager,
    )


@lru_cache
def get_openrouter_service() -> OpenRouterService:
    return OpenRouterService()


@lru_cache
def get_connection_manager() -> ConnectionManager:
    return ConnectionManager()


@lru_cache
def get_realtime_event_service() -> RealtimeEventService:
    return RealtimeEventService(manager=get_connection_manager())


@lru_cache
def get_extraction_service() -> ExtractionService:
    return ExtractionService(openrouter_service=get_openrouter_service())


@lru_cache
def get_profile_service() -> ProfileService:
    archive_path = get_settings().resolved_memory_json_path / "archive"
    return ProfileService(memory_service=get_memory_service(), archive_path=archive_path)


@lru_cache
def get_simulation_service() -> SimulationService:
    return SimulationService(
        profile_service=get_profile_service(),
        memory_service=get_memory_service(),
        openrouter_service=get_openrouter_service(),
    )


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        memory_service=get_memory_service(),
        openrouter_service=get_openrouter_service(),
        extraction_service=get_extraction_service(),
        profile_service=get_profile_service(),
        realtime_event_service=get_realtime_event_service(),
    )
