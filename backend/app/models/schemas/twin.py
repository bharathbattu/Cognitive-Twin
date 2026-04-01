from typing import Any
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TwinProfileResponse(BaseModel):
    session_id: str
    summary: str
    memory_count: int
    latest_topics: list[str]
    twin_status: Literal["training", "deployed"]


class TwinLifecycleTransitionResponse(BaseModel):
    message: str
    new_session_id: str | None = None
    previous_session_archived: bool


class SimulationRequest(BaseModel):
    session_id: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    debug: bool = False

    @field_validator("session_id", "scenario", mode="before")
    @classmethod
    def normalize_non_empty_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("Value must be a string.")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Value cannot be empty.")
        return normalized


class SimulationResponse(BaseModel):
    decision: str
    reasoning: str
    debug: dict[str, Any] | None = None
