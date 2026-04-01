from fastapi import APIRouter, Depends

from app.core.dependencies import get_memory_service, get_realtime_event_service
from app.models.schemas.common import ApiResponse, success_response
from app.models.schemas.memory import MemoryCreateRequest, MemoryListResponse
from app.services.memory.memory_service import MemoryService
from app.services.twin.realtime_service import RealtimeEventService

router = APIRouter()


@router.get("/{session_id}", response_model=ApiResponse[MemoryListResponse])
async def list_memories(
    session_id: str,
    memory_service: MemoryService = Depends(get_memory_service),
) -> ApiResponse[MemoryListResponse]:
    return success_response(memory_service.list_memories(session_id))


@router.post("/{session_id}", response_model=ApiResponse[MemoryListResponse])
async def add_memory(
    session_id: str,
    payload: MemoryCreateRequest,
    memory_service: MemoryService = Depends(get_memory_service),
    realtime_event_service: RealtimeEventService = Depends(get_realtime_event_service),
) -> ApiResponse[MemoryListResponse]:
    memory_service.remember(session_id=session_id, text=payload.text, metadata=payload.metadata)
    memory_list = memory_service.list_memories(session_id)
    await realtime_event_service.publish(
        session_id=session_id,
        event_type="memory_update",
        data=memory_list.model_dump(mode="json"),
    )
    return success_response(memory_list)
