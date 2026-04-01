from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = Field(default="default-session")
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("message", "session_id", mode="before")
    @classmethod
    def normalize_non_empty_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("Value must be a string.")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Value cannot be empty.")
        return normalized


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    model: str
    memory_hits: list[dict[str, Any]]
