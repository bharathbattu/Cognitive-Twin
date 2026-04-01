from contextlib import asynccontextmanager
import logging
import time

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.dependencies import get_connection_manager
from app.core.logging import configure_logging
from app.services.twin.realtime_service import parse_json_message
from app.utils.file_helpers import ensure_directory


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging()
    ensure_directory(settings.resolved_memory_json_path)
    ensure_directory(settings.resolved_memory_faiss_path)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
logger = logging.getLogger(__name__)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    logger.info("Request start method='%s' path='%s'", request.method, request.url.path)

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "Request failed method='%s' path='%s' duration_ms=%.2f",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - start_time) * 1000
    level = logging.INFO
    if response.status_code >= 500:
        level = logging.ERROR
    elif response.status_code >= 400:
        level = logging.WARNING

    logger.log(
        level,
        "Request end method='%s' path='%s' status=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

if settings.cors_allow_origin_regex:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.resolved_frontend_origins,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.resolved_frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception for path '%s'", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": str(exc),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": str(exc.detail),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "error": "Validation error",
            "details": jsonable_encoder(exc.errors()),
        },
    )


@app.get("/health")
async def root_health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    manager = get_connection_manager()
    await manager.connect(session_id=session_id, websocket=websocket)
    await manager.send_update(
        session_id=session_id,
        data={
            "type": "memory_update",
            "data": {"session_id": session_id, "status": "connected"},
        },
    )
    try:
        while True:
            raw_message = await websocket.receive_text()
            payload = parse_json_message(raw_message)
            if payload.get("type") == "ping":
                await websocket.send_json({"type": "pong", "data": {"session_id": session_id}})
    except WebSocketDisconnect:
        await manager.disconnect(session_id=session_id, websocket=websocket)
    except Exception:
        logger.exception("WebSocket error for session '%s'", session_id)
        await manager.disconnect(session_id=session_id, websocket=websocket)


app.include_router(api_router, prefix=settings.api_v1_prefix)
