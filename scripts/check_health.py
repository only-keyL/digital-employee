"""Health check script for Phase 1 acceptance."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings


def main() -> int:
    url = settings.health_check_url
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[FAIL] Unable to reach health endpoint: {url}")
        print(f"       Error: {exc}")
        print(
            "       Make sure the server is running: "
            "python -m uvicorn app.main:app --reload --host 127.0.0.1 --port <APP_PORT>"
        )
        return 1

    status = payload.get("status")
    module = payload.get("module")
    env = payload.get("env")

    if status != "ok":
        print(f"[FAIL] status expected 'ok', got {status!r}")
        return 1

    if module != "digital-employee-assistant":
        print(f"[FAIL] module expected 'digital-employee-assistant', got {module!r}")
        return 1

    print(f"[PASS] Health check OK: status={status}, module={module}, env={env}")
    print(f"       URL: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
