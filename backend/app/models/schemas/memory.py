from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MemoryCreateRequest(BaseModel):
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_non_empty_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("Value must be a string.")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Value cannot be empty.")
        return normalized


class MemoryItem(BaseModel):
    id: str
    role: str
    text: str
    metadata: dict[str, Any]
    created_at: datetime


class MemoryListResponse(BaseModel):
    session_id: str
    count: int
    items: list[MemoryItem]
