"""后台管理 Token 鉴权（阶段 6 轻量保护，生产应接正式登录/RBAC）。"""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.config.settings import get_settings


def require_admin_auth(request: Request) -> None:
    """校验后台管理 Token；ADMIN_AUTH_ENABLED=false 时直接放行（dev 默认）。"""
    settings = get_settings()
    if not settings.admin_auth_enabled:
        return

    header_name = settings.admin_token_header
    token = request.headers.get(header_name)
    if not token and request.url.path.startswith("/admin"):
        token = request.query_params.get("admin_token")

    expected = (settings.admin_token or "").strip()
    if not expected:
        raise HTTPException(status_code=401, detail="后台鉴权已开启但未配置 ADMIN_TOKEN")

    if not token or token.strip() != expected:
        raise HTTPException(status_code=401, detail="未授权：后台管理 Token 无效或缺失")
