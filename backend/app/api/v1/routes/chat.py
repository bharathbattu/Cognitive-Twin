from fastapi import APIRouter, Depends

from app.models.schemas.common import ApiResponse, success_response
from app.core.dependencies import get_chat_service
from app.models.schemas.chat import ChatRequest, ChatResponse
from app.services.twin.chat_service import ChatService

router = APIRouter()


@router.post("", response_model=ApiResponse[ChatResponse])
async def chat_with_twin(
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ApiResponse[ChatResponse]:
    response = await chat_service.chat(payload)
    return success_response(response)
