"""企业微信回调路由：URL 验证、真实 XML 回调与 Mock JSON。

这个文件属于 Router 层，也可以理解成 Java 里的 Controller。

它只负责三件事：
1. 定义企业微信相关 URL；
2. 从 HTTP 请求里拿参数 / 请求体 / 数据库 Session；
3. 调用 WecomCallbackService，把真正业务处理交给 Service。

注意：
这里不直接做知识库检索、不直接生成答案。
真正的企业微信消息处理在 app/services/wecom_callback_service.py。
"""

# 延迟解析类型标注，减少运行时类型引用带来的兼容问题。
from __future__ import annotations

# APIRouter：FastAPI 的路由分组对象，类似 Spring 里的一个 Controller 类。
# Depends：依赖注入，用来注入数据库 Session 等对象。
# Query：声明 query string 参数，例如 ?echostr=xxx。
# Request：表示原始 HTTP 请求对象，可以从里面读取 body。
from fastapi import APIRouter, Depends, Query, Request

# FastAPI 响应类型：
# - JSONResponse：返回 JSON；
# - PlainTextResponse：返回普通文本；
# - Response：通用响应，可以指定 XML 等 media_type。
from fastapi.responses import JSONResponse, PlainTextResponse, Response

# SQLAlchemy 的数据库会话类型。
from sqlalchemy.orm import Session

# settings 是系统配置，例如 WECOM_ENABLED 是否开启真实企微入口。
from app.config.settings import settings

# get_db 是 FastAPI 依赖函数：每次请求进来时创建数据库 Session，请求结束后关闭。
from app.db.database import get_db

# 企业微信回调业务服务。
# Router 收到请求后，会把参数交给它处理。
from app.services.wecom_callback_service import WecomCallbackService

# 本地 Mock 企业微信回调的 JSON 请求体模型。
from app.wecom.schemas import WecomMockCallbackRequest

# 创建一个企业微信路由分组。
#
# prefix="/api/wecom" 表示本文件里所有路由都会自动加这个前缀。
# 例如下面写 @router.get("/callback")，真实完整路径就是：
# GET /api/wecom/callback
#
# tags=["wecom"] 用于 OpenAPI/Swagger 文档分组。
router = APIRouter(prefix="/api/wecom", tags=["wecom"])


# GET /api/wecom/callback
#
# 真实企业微信后台配置“接收消息 URL”时，会先发 GET 请求做 URL 验证。
# 验证通过后，企业微信才会认可这个回调地址。
@router.get("/callback")
def wecom_url_verify(
    # Query(default=None) 表示这些参数从 URL query string 里取。
    # 例如：
    # /api/wecom/callback?msg_signature=xxx&timestamp=xxx&nonce=xxx&echostr=xxx
    #
    # `str | None` 表示这个参数可以是字符串，也可以不存在。
    msg_signature: str | None = Query(default=None),
    timestamp: str | None = Query(default=None),
    nonce: str | None = Query(default=None),
    echostr: str | None = Query(default=None),

    # Depends(get_db) 表示让 FastAPI 自动调用 get_db()，注入当前请求的数据库 Session。
    # 这个接口本身主要做 URL 验证，一般不写业务数据，但 Service 构造仍保持统一传 db。
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """企业微信 GET 回调 URL 验证（验签并返回 echostr）。

    返回 PlainTextResponse 是因为企业微信 URL 验证要求直接返回纯文本 echostr，
    不是 JSON，也不是 XML。
    """

    # 创建企业微信回调服务，把请求级数据库 Session 传进去。
    service = WecomCallbackService(db)

    # 调用 Service 完成验签 / echostr 解密等逻辑。
    result = service.verify_callback_url(
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
        echostr=echostr,
    )

    # 企业微信要求 URL 验证时返回 echostr 明文，所以这里返回纯文本。
    return PlainTextResponse(content=result)


# POST /api/wecom/callback
#
# 这是预留给真实企业微信的消息回调入口。
# 用户给企业微信应用发消息后，企业微信会把 XML POST 到这个地址。
@router.post("/callback", response_model=None)
async def wecom_real_callback(
    # Request 是原始 HTTP 请求对象。
    # 因为真实企业微信发来的是 XML，不是 Pydantic JSON 模型，所以这里用 Request 读取原始 body。
    request: Request,

    # 这些 query 参数用于真实企业微信 POST 消息验签。
    msg_signature: str | None = Query(default=None),
    timestamp: str | None = Query(default=None),
    nonce: str | None = Query(default=None),

    # 当前请求数据库 Session。
    db: Session = Depends(get_db),
) -> Response:
    """企业微信真实 POST 消息回调，返回被动回复 XML。

    语法解释：
    - async def 表示这是异步接口函数；
    - await request.body() 表示等待读取请求体；
    - response_model=None 表示不让 FastAPI 按 Pydantic 模型包装响应。
    """

    # MVP 默认关闭真实企业微信入口。
    # 如果 WECOM_ENABLED=false，直接返回 503，避免误以为生产接入已完成。
    if not settings.wecom_enabled:
        return JSONResponse(status_code=503, content={"error": "wecom disabled"})

    # 创建企业微信回调服务。
    service = WecomCallbackService(db)

    # 企业微信真实消息体是 XML 字符串。
    # request.body() 得到 bytes，需要 decode("utf-8") 转成 str。
    body = (await request.body()).decode("utf-8")

    # 交给 Service 处理真实 XML：
    # - 验签；
    # - 必要时解密；
    # - 解析 XML；
    # - 转 AskRequest；
    # - 调 AskService；
    # - 返回企业微信 XML。
    xml_body = service.handle_real_callback(
        body,
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
    )

    # 企业微信回调要求返回 XML。
    # media_type="application/xml" 告诉调用方响应内容是 XML。
    return Response(content=xml_body, media_type="application/xml")


# POST /api/wecom/mock/callback
#
# 这是本地开发 / MVP 演示用入口。
# 不需要真实企业微信账号，不需要 XML，直接 POST JSON 即可模拟企微消息。
@router.post("/mock/callback", response_model=None)
def wecom_mock_callback(
    # FastAPI 会自动把 JSON 请求体解析成 WecomMockCallbackRequest。
    # 如果字段不符合模型要求，会自动返回参数校验错误。
    payload: WecomMockCallbackRequest,

    # 当前请求数据库 Session。
    db: Session = Depends(get_db),
) -> Response:
    """本地 Mock 企业微信回调（JSON 入参），用于开发演示。

    这个入口是 MVP 当前主验收入口。
    它和真实回调最终都会走 WecomCallbackService，只是入参格式不同：
    - Mock：JSON -> WecomMockCallbackRequest；
    - 真实：XML -> 原始 body 字符串。
    """

    # 创建企业微信回调服务。
    service = WecomCallbackService(db)

    # 处理 Mock JSON，返回企业微信被动回复 XML 字符串。
    xml_body = service.handle_mock_callback(payload)

    # 虽然请求是 JSON，但为了模拟企业微信被动回复，响应仍然返回 XML。
    return Response(content=xml_body, media_type="application/xml")
