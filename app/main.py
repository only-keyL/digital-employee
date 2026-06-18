"""FastAPI 应用入口文件。

这个文件是整个 Web 服务的“总开关”：
1. 创建 FastAPI 应用对象；
2. 挂载静态资源目录；
3. 注册各个业务路由；
4. 暴露 app 给 uvicorn 启动。

本项目启动命令里的 `app.main:app` 指的就是本文件最后的 `app` 变量。
"""

# pathlib.Path 是 Python 标准库里的路径工具。
# 比手写字符串拼路径更安全，Windows / Linux 都能兼容。
from pathlib import Path

# FastAPI 是 Web 框架的核心类，用来创建应用实例。
from fastapi import FastAPI

# StaticFiles 用来让 FastAPI 对外提供静态文件，比如 CSS、JS、图片。
from fastapi.staticfiles import StaticFiles

# settings 是项目配置对象，里面包含应用名、debug 开关、数据库地址等配置。
from app.config.settings import settings
from app.core.runtime_check import run_runtime_check

# 下面这些 router 可以理解成一组组 Controller。
# 每个 router 负责一类 URL：
# - page_router：页面路由；
# - api_router：健康检查等通用 API；
# - ask_router：问答 API；
# - knowledge_router：知识卡片；
# - unanswered_router：未命中问题；
# - feedback_router：反馈；
# - statistics_router：统计；
# - wecom_router：企业微信回调。
from app.routers.api_router import router as api_router
from app.routers.ask_router import router as ask_router
from app.routers.ask_v2_router import router as ask_v2_router
from app.routers.knowledge_router import router as knowledge_router
from app.routers.page_router import router as page_router
from app.routers.feedback_router import router as feedback_router
from app.routers.infra_router import router as infra_router
from app.routers.mock_wecom_router import router as mock_wecom_router
from app.routers.statistics_router import router as statistics_router
from app.routers.unanswered_router import router as unanswered_router
from app.routers.wecom_router import router as wecom_router

# 当前文件所在目录：.../app
#
# 语法解释：
# - __file__ 表示当前 Python 文件路径；
# - Path(__file__) 把字符串路径转成 Path 对象；
# - resolve() 转成绝对路径；
# - parent 取父目录。
BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例，挂载静态资源与各业务路由。

    小白理解：
    这个函数就像 Spring Boot 里的应用初始化配置。
    它把“应用基本信息”“静态文件目录”“各个 Controller”都装配到一起。
    """

    # 启动前执行运行时配置检查：dev/test 仅 warning，prod 配置错误则阻止启动。
    run_runtime_check(settings)

    # 创建 FastAPI 应用对象。
    # title 会显示在 OpenAPI/Swagger 文档里。
    # debug 控制是否开启调试模式，来自配置文件。
    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
    )

    # app/static 目录用于存放前端静态资源，例如：
    # - app/static/css/main.css
    # - app/static/js/main.js
    static_dir = BASE_DIR / "static"

    # 把静态资源目录挂到 URL 前缀 /static。
    #
    # 例如浏览器访问：
    # /static/css/main.css
    # FastAPI 会去读取：
    # app/static/css/main.css
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 注册页面路由：例如首页、列表页、详情页等 HTML 页面。
    app.include_router(page_router)

    # 注册通用 API：例如 /api/health。
    app.include_router(api_router)

    # 注册基础设施健康检查 API：/api/infra/health。
    app.include_router(infra_router)

    # 注册问答 API：例如 POST /api/ask。
    app.include_router(ask_router)

    # 注册 Stage3 RAG 问答 API：/api/ask-v2、/api/mock/ask-v2。
    app.include_router(ask_v2_router)

    # 注册 Stage4 模拟企微入口：/api/mock/wecom/message。
    app.include_router(mock_wecom_router)

    # 注册知识卡片相关 API / 页面操作。
    app.include_router(knowledge_router)

    # 注册未命中问题相关 API / 页面操作。
    app.include_router(unanswered_router)

    # 注册用户反馈相关 API。
    app.include_router(feedback_router)

    # 注册统计看板相关 API。
    app.include_router(statistics_router)

    # 注册企业微信回调相关 API：
    # - GET/POST /api/wecom/callback
    # - POST /api/wecom/mock/callback
    app.include_router(wecom_router)

    return app


# uvicorn 启动时会读取这个变量。
#
# 启动命令：
# python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
#
# 其中：
# - app.main 表示导入 app/main.py；
# - :app 表示取本文件里的 app 变量；
# - app 变量是 create_app() 创建出来的 FastAPI 实例。
app = create_app()
