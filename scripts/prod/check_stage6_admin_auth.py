#!/usr/bin/env python
"""Stage6 后台 Token 鉴权验收（不修改 docs/prod/.env）。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.config.settings import get_settings
from app.core.settings import apply_env_file

DEFAULT_ENV_FILE = "docs/prod/.env"
TEST_TOKEN_PLACEHOLDER = "stage6-auth-check-token-placeholder"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage6 后台鉴权验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def _build_client() -> tuple[TestClient, str]:
    """临时开启鉴权并注入测试 Token，不写入真实 env 文件。"""
    os.environ["ADMIN_AUTH_ENABLED"] = "true"
    token = (os.environ.get("ADMIN_TOKEN") or "").strip()
    if not token:
        os.environ["ADMIN_TOKEN"] = TEST_TOKEN_PLACEHOLDER
        token = TEST_TOKEN_PLACEHOLDER
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    return TestClient(app), token


def main() -> int:
    args = parse_args()
    apply_env_file(args.env_file)
    client, token = _build_client()
    header_name = get_settings().admin_token_header

    print("=" * 60)
    print("Stage6 后台鉴权验收")
    print("=" * 60)

    failed = 0

    r = client.get("/api/admin/contributions")
    if r.status_code == 401:
        print("[PASS] 无 Token 访问 /api/admin/contributions 返回 401")
    else:
        print(f"[FAIL] 无 Token 应返回 401，实际 {r.status_code}")
        failed += 1

    r = client.get("/api/admin/contributions", headers={header_name: "wrong-token-value"})
    if r.status_code == 401:
        print("[PASS] 错误 Token 访问后台 API 返回 401")
    else:
        print(f"[FAIL] 错误 Token 应返回 401，实际 {r.status_code}")
        failed += 1

    r = client.get("/api/admin/contributions", headers={header_name: token})
    if r.status_code == 200:
        print("[PASS] 正确 Token 访问后台 API 返回 200")
    else:
        print(f"[FAIL] 正确 Token 应返回 200，实际 {r.status_code}")
        failed += 1

    r = client.get("/admin/contributions")
    if r.status_code == 401:
        print("[PASS] 无 Token 访问 /admin/contributions 返回 401")
    else:
        print(f"[FAIL] 无 Token 页面应返回 401，实际 {r.status_code}")
        failed += 1

    r = client.get("/admin/contributions", params={"admin_token": token})
    if r.status_code == 200:
        print("[PASS] 页面可通过 admin_token 查询参数访问")
    else:
        print(f"[FAIL] 页面带正确 admin_token 应返回 200，实际 {r.status_code}")
        failed += 1

    r = client.get("/api/health")
    if r.status_code == 200:
        print("[PASS] /api/health 不受后台鉴权影响")
    else:
        print(f"[FAIL] /api/health 应返回 200，实际 {r.status_code}")
        failed += 1

    print("-" * 60)
    if failed:
        print(f"[结果] 失败：{failed} 项未通过")
        return 1
    print("[结果] 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] 鉴权验收异常：{exc}")
        raise SystemExit(1) from exc
