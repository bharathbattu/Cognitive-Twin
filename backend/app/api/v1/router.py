from fastapi import APIRouter

from app.api.v1.routes import chat, health, memory, twin

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(twin.router, prefix="/twin", tags=["twin"])
