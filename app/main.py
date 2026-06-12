from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.routers.api_router import router as api_router
from app.routers.ask_router import router as ask_router
from app.routers.knowledge_router import router as knowledge_router
from app.routers.page_router import router as page_router
from app.routers.feedback_router import router as feedback_router
from app.routers.statistics_router import router as statistics_router
from app.routers.unanswered_router import router as unanswered_router
from app.routers.wecom_router import router as wecom_router

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例，挂载静态资源与各业务路由。"""
    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
    )

    static_dir = BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(page_router)
    app.include_router(api_router)
    app.include_router(ask_router)
    app.include_router(knowledge_router)
    app.include_router(unanswered_router)
    app.include_router(feedback_router)
    app.include_router(statistics_router)
    app.include_router(wecom_router)

    return app


app = create_app()
