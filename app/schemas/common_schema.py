"""通用 API 响应结构。"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应包装：success / data / message。"""

    success: bool = Field(..., description="请求是否成功")
    data: T | None = Field(default=None, description="业务数据载荷")
    message: str = Field(default="ok", description="提示信息")


def success_response(data: Any = None, message: str = "ok") -> dict:
    """构造成功响应字典。"""
    return {"success": True, "data": data, "message": message}


def error_response(message: str) -> dict:
    """构造失败响应字典。"""
    return {"success": False, "data": None, "message": message}
