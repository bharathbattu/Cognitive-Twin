from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    id: str
    session_id: str
    text: str
    role: str = "memory"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
