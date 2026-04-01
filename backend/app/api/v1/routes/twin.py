import logging

from fastapi import APIRouter, Depends

from app.core.dependencies import get_memory_service, get_profile_service, get_realtime_event_service, get_simulation_service
from app.models.schemas.common import ApiResponse, success_response
from app.models.schemas.twin import (
    SimulationRequest,
    SimulationResponse,
    TwinLifecycleTransitionResponse,
    TwinProfileResponse,
)
from app.services.twin.profile_service import ProfileService
from app.services.twin.realtime_service import RealtimeEventService
from app.services.twin.simulation_service import SimulationService
from app.services.memory.memory_service import MemoryService

router = APIRouter()
logger = logging.getLogger(__name__)
RECENT_USER_INTERACTIONS_LIMIT = 9


def _normalize_interaction_text(text: str, max_chars: int = 400) -> str:
    compact_text = " ".join(text.strip().split())
    if len(compact_text) <= max_chars:
        return compact_text
    return f"{compact_text[: max_chars - 3].rstrip()}..."


def _collect_recent_user_interactions(memory_service: MemoryService, session_id: str) -> list[dict[str, str]]:
    user_entries = memory_service.get_memories(session_id=session_id, role="user")
    recent_entries = user_entries[-RECENT_USER_INTERACTIONS_LIMIT:]
    return [
        {
            "id": entry.id,
            "text": _normalize_interaction_text(entry.text),
            "created_at": entry.created_at.isoformat(),
        }
        for entry in recent_entries
    ]


def _build_simulation_memory_text(
    payload: SimulationRequest,
    result: SimulationResponse,
    recent_user_interactions: list[dict[str, str]],
) -> str:
    lines = [
        f"Simulation scenario: {payload.scenario}\n"
        f"Decision: {result.decision}\n"
        f"Reasoning: {result.reasoning}"
    ]

    if recent_user_interactions:
        lines.append("Recent user interactions considered:")
        lines.extend(f"- {interaction['text']}" for interaction in recent_user_interactions)

    return "\n".join(lines)


async def _sync_simulation_side_effects(
    payload: SimulationRequest,
    result: SimulationResponse,
    memory_service: MemoryService,
    realtime_event_service: RealtimeEventService,
    is_fallback: bool,
) -> None:
    try:
        recent_user_interactions = _collect_recent_user_interactions(memory_service, payload.session_id)
        memory_service.remember(
            session_id=payload.session_id,
            text=_build_simulation_memory_text(payload, result, recent_user_interactions),
            metadata={
                "source": "simulation_engine",
                "simulation": {
                    "scenario": payload.scenario,
                    "decision": result.decision,
                    "reasoning": result.reasoning,
                    "debug": result.debug,
                    "is_fallback": is_fallback,
                    "recent_user_interaction_count": len(recent_user_interactions),
                    "recent_user_interactions": recent_user_interactions,
                },
            },
            role="memory",
        )
        memory_list = memory_service.list_memories(payload.session_id)
        await realtime_event_service.publish(
            session_id=payload.session_id,
            event_type="memory_update",
            data=memory_list.model_dump(mode="json"),
        )
        await realtime_event_service.publish(
            session_id=payload.session_id,
            event_type="simulation_result",
            data=result.model_dump(mode="json", exclude_none=True),
        )
    except Exception:
        logger.exception("Simulation side-effect sync failed for session '%s'.", payload.session_id)


@router.get("/{session_id}/profile", response_model=ApiResponse[TwinProfileResponse])
async def get_twin_profile(
    session_id: str,
    profile_service: ProfileService = Depends(get_profile_service),
) -> ApiResponse[TwinProfileResponse]:
    return success_response(profile_service.build_profile(session_id))


@router.post("/{session_id}/lifecycle/transition", response_model=ApiResponse[TwinLifecycleTransitionResponse])
async def transition_twin_lifecycle(
    session_id: str,
    profile_service: ProfileService = Depends(get_profile_service),
) -> ApiResponse[TwinLifecycleTransitionResponse]:
    result = profile_service.transition_lifecycle_if_deployed(session_id)
    return success_response(TwinLifecycleTransitionResponse.model_validate(result))


@router.post("/simulate", response_model=ApiResponse[SimulationResponse])
async def simulate_twin_decision(
    payload: SimulationRequest,
    simulation_service: SimulationService = Depends(get_simulation_service),
    memory_service: MemoryService = Depends(get_memory_service),
    realtime_event_service: RealtimeEventService = Depends(get_realtime_event_service),
) -> ApiResponse[SimulationResponse]:
    logger.info("Received simulation request for session '%s' (debug=%s)", payload.session_id, payload.debug)
    is_fallback = False
    try:
        result = simulation_service.simulate_decision(
            session_id=payload.session_id,
            scenario=payload.scenario,
            debug=payload.debug,
        )
        logger.info("Simulation completed for session '%s' (debug=%s)", payload.session_id, payload.debug)
        response_model = SimulationResponse.model_validate(result)
    except Exception:
        is_fallback = True
        logger.exception("Simulation failed for session '%s' (debug=%s)", payload.session_id, payload.debug)
        fallback_payload = {
            "decision": "The user would pause until they can evaluate this more reliably.",
            "reasoning": "The simulation service is temporarily unavailable, so this is a controlled fallback response.",
        }
        response_model = SimulationResponse.model_validate(fallback_payload)

    await _sync_simulation_side_effects(
        payload=payload,
        result=response_model,
        memory_service=memory_service,
        realtime_event_service=realtime_event_service,
        is_fallback=is_fallback,
    )
    return success_response(response_model)
