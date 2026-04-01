from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: str | None = None


def success_response(data: T) -> ApiResponse[T]:
    return ApiResponse(success=True, data=data, error=None)


def error_response(message: str) -> ApiResponse[None]:
    return ApiResponse(success=False, data=None, error=message)
