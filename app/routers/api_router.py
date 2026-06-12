"""通用 API 路由（健康检查等）。"""

from fastapi import APIRouter

from app.config.settings import settings

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """服务健康检查，返回运行环境与模块名。"""
    return {
        "status": "ok",
        "module": "digital-employee-assistant",
        "env": settings.app_env,
    }
