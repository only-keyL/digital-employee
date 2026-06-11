from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    message: str = "ok"


def success_response(data: Any = None, message: str = "ok") -> dict:
    return {"success": True, "data": data, "message": message}


def error_response(message: str) -> dict:
    return {"success": False, "data": None, "message": message}
