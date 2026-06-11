from fastapi import APIRouter

from app.config.settings import settings

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "module": "digital-employee-assistant",
        "env": settings.app_env,
    }
