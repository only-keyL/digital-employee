"""基础设施健康检查 API。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.config.settings import settings
from app.services.infra_health_service import InfraHealthService

router = APIRouter(prefix="/api/infra", tags=["infra"])


@router.get("/health")
async def infra_health(
    deep: bool = Query(default=False, description="是否执行真实外部依赖调用"),
    allow_qdrant_write: bool = Query(
        default=False,
        description="deep 模式下是否允许 Qdrant 写入固定测试向量",
    ),
) -> dict:
    """基础设施健康检查：默认 shallow，deep=true 时发起真实调用。"""
    service = InfraHealthService(settings)
    return await service.check_all(deep=deep, allow_qdrant_write=allow_qdrant_write)
