from fastapi import APIRouter

from app.core.config import get_settings
from app.models.schemas.common import ApiResponse, success_response
from app.models.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=ApiResponse[HealthResponse])
async def health_check() -> ApiResponse[HealthResponse]:
    settings = get_settings()
    payload = HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
    )
    return success_response(payload)
