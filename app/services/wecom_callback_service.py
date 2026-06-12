"""企业微信回调编排服务。

这个文件可以理解成“企业微信适配器”：
1. 企业微信把消息推给我们；
2. 这里负责校验、解析、去重；
3. 然后把企微消息转成项目内部统一的 AskRequest；
4. 调用 AskService 走问答主链路；
5. 最后把 AskResponse 转成企业微信要求的 XML 返回。

注意：这个文件不真正负责“怎么检索知识库、怎么生成答案”。
真正问答逻辑在 AskService / LangGraph / RetrievalService 里。
"""

# 让类型标注在运行时延迟解析。
# 小白理解：这是 Python 的一个兼容写法，可以让 `A | None`、类名类型标注更好用，
# 避免某些类型在文件加载时还没准备好就报错。
from __future__ import annotations

import logging
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.schemas.ask_schema import AskRequest
from app.services.ask_service import AskService
from app.wecom.constants import (
    DEFAULT_GROUP_ID,
    EMPTY_CONTENT_REPLY,
    MSG_TYPE_TEXT,
    SOURCE_TYPE_WECOM,
    UNSUPPORTED_MSG_REPLY,
)
from app.wecom.crypto import decrypt_echostr, decrypt_message_body
from app.wecom.dedup_store import WecomDedupStore
from app.wecom.message_parser import parse_mock_request, parse_plain_xml
from app.wecom.response_builder import build_fixed_reply, build_text_reply
from app.wecom.schemas import WecomInboundMessage, WecomMockCallbackRequest
from app.wecom.url_verify import verify_signature

# logger 是当前模块的日志对象。
# __name__ 会等于当前模块路径，例如 app.services.wecom_callback_service。
# 后面 logger.warning(...) 会把告警打到日志里，方便排查生产问题。
logger = logging.getLogger(__name__)

# 进程内全局去重缓存。
#
# 语法解释：
# - 变量名前面的 `_` 表示“内部使用”，不是强制私有，只是 Python 约定。
# - `WecomDedupStore | None` 表示这个变量可能是 WecomDedupStore，也可能是 None。
# - 初始值为 None，表示还没有创建真正的去重缓存对象。
#
# 业务解释：
# 企业微信可能因为网络等原因重复推送同一条 msg_id。
# 如果不去重，同一条消息会重复问答、重复写日志、重复增加未命中次数。
_dedup_store: WecomDedupStore | None = None


def _get_dedup_store(settings: Settings) -> WecomDedupStore:
    """获取全局去重缓存，懒加载创建。

    语法解释：
    - `global _dedup_store` 表示函数里要修改模块级变量 _dedup_store。
    - 如果不写 global，Python 会把 `_dedup_store = ...` 当成函数内部局部变量。

    业务解释：
    - 第一次调用时创建 WecomDedupStore；
    - 后续请求复用同一个去重缓存；
    - 这样同一个进程内可以记住最近处理过的企业微信 msg_id。
    """

    global _dedup_store
    if _dedup_store is None:
        _dedup_store = WecomDedupStore(ttl_seconds=settings.wecom_dedup_ttl_seconds)
    return _dedup_store


class WecomCallbackService:
    """企业微信回调编排：验签、解密、去重，复用 AskService 生成回复。

    Java 后端类比：
    - 这个类类似一个 WecomCallbackApplicationService；
    - Router/Controller 收到请求后，把请求交给它；
    - 它负责协调 parser、dedup、AskService、response_builder。
    """

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        """初始化服务对象。

        参数解释：
        - session: 当前请求的数据库 Session，后面传给 AskService 写 question_log 等数据。
        - settings: 系统配置。默认不传，使用 get_settings() 获取全局配置。

        语法解释：
        - `settings: Settings | None = None` 表示 settings 可以传 Settings，也可以不传。
        - `settings or get_settings()` 表示：
          如果 settings 有值就用它；否则调用 get_settings()。
        """

        self.session = session
        self.settings = settings or get_settings()
        self.dedup_store = _get_dedup_store(self.settings)

    def verify_callback_url(
        self,
        *,
        msg_signature: str | None,
        timestamp: str | None,
        nonce: str | None,
        echostr: str | None,
    ) -> str:
        """处理企业微信 GET 回调 URL 验证，返回 echostr 明文。

        企业微信真实接入时，后台保存“接收消息 URL”会先发一个 GET 请求。
        我们需要按企业微信规则校验签名，然后返回 echostr，企业微信才认为 URL 可用。

        语法解释：
        - 参数列表中的单独 `*` 表示后面的参数必须用关键字传参。
          例如必须写 verify_callback_url(msg_signature=..., timestamp=...)。
          这样可以避免多个字符串参数顺序写错。
        - `-> str` 表示这个函数返回字符串。
        """

        # echostr 是企业微信 URL 验证必须带的随机字符串。
        # 没有它就无法完成验证，所以直接返回 400。
        if not echostr:
            raise HTTPException(status_code=400, detail="missing echostr")

        # MVP 默认 WECOM_ENABLED=false。
        # 关闭真实企微接入时，不做验签，直接返回 echostr，方便本地 Mock 验收。
        if not self.settings.wecom_enabled:
            return echostr

        token = self.settings.wecom_token
        # 真实验签必须依赖企业微信后台配置的 Token。
        if not token:
            raise HTTPException(status_code=403, detail="wecom token not configured")

        # 企业微信传来的 query 参数可能是 None。
        # `or ""` 是为了把 None 转成空字符串，避免 verify_signature 里处理 None。
        signature = msg_signature or ""
        ts = timestamp or ""
        nc = nonce or ""

        # verify_signature 会按企业微信规则计算 SHA1 签名并比对。
        # 签名不对，说明请求可能不是企业微信发来的，直接拒绝。
        if not verify_signature(
            token=token,
            timestamp=ts,
            nonce=nc,
            msg_signature=signature,
            echostr=echostr,
        ):
            raise HTTPException(status_code=403, detail="invalid signature")

        # 如果配置了 EncodingAESKey，理论上 echostr 需要解密。
        # 当前项目 AES 是预留能力，能解出来就返回明文；解不出来则降级返回原 echostr。
        if self.settings.wecom_encoding_aes_key:
            decrypted = decrypt_echostr(
                encoding_aes_key=self.settings.wecom_encoding_aes_key,
                echostr=echostr,
            )
            if decrypted:
                return decrypted

        return echostr

    def handle_mock_callback(self, payload: WecomMockCallbackRequest) -> str:
        """处理本地 Mock JSON 回调，返回被动回复 XML。

        这是 MVP 演示时最常用的入口：
        - 不需要真实企业微信；
        - 直接 POST JSON；
        - 但后续会复用和真实企微一样的问答链路。
        """

        # 如果配置禁用了 Mock 入口，则返回 503。
        # HTTPException 是 FastAPI 提供的异常，抛出后会自动转成 HTTP 响应。
        if not self.settings.wecom_mock_enabled:
            raise HTTPException(status_code=503, detail="wecom mock disabled")

        # 把 Mock JSON DTO 转成项目内部统一的 WecomInboundMessage。
        # 后续代码不再关心消息来自 Mock JSON 还是真实 XML。
        message = parse_mock_request(payload)

        # 进入统一入站消息处理逻辑。
        return self._handle_inbound_message(message)

    def handle_real_callback(
        self,
        body: str,
        *,
        msg_signature: str | None = None,
        timestamp: str | None = None,
        nonce: str | None = None,
    ) -> str:
        """处理真实企业微信 POST XML 回调，验签解密后生成回复。

        真实企业微信发消息时，会 POST XML 到 `/api/wecom/callback`。
        这个方法负责处理真实 XML，不处理 Mock JSON。

        参数解释：
        - body: HTTP 请求体里的 XML 字符串。
        - msg_signature/timestamp/nonce: 企业微信用于验签的 query 参数。
        """

        # 真实企微入口默认关闭，避免没有配置 Token/AES/公网环境时误用。
        if not self.settings.wecom_enabled:
            raise HTTPException(status_code=503, detail="wecom disabled")

        # `(body or "").strip()`：
        # - body 如果是 None 或空值，就用 "";
        # - strip() 去掉前后空白字符。
        raw_body = (body or "").strip()
        if not raw_body:
            raise HTTPException(status_code=400, detail="empty body")

        # 企业微信生产环境常见的是加密 XML，里面会有 <Encrypt>。
        # 当前项目的 AES 解密仍是预留能力，所以这里能解就继续，不能解就返回“不支持”话术。
        if self.settings.wecom_encoding_aes_key and "<Encrypt>" in raw_body:
            decrypted = decrypt_message_body(
                encoding_aes_key=self.settings.wecom_encoding_aes_key,
                body=raw_body,
            )
            if decrypted:
                # 解密成功后，后续就按普通明文 XML 继续解析。
                raw_body = decrypted
            else:
                logger.warning("Encrypted WeCom callback received but AES decrypt is not available.")

                # 构造一个占位消息对象，用来生成企业微信要求的 XML 回复。
                # f"unsupported-{int(time.time())}" 是 f-string，用当前时间拼一个临时 msg_id。
                placeholder = WecomInboundMessage(
                    msg_id=f"unsupported-{int(time.time())}",
                    from_user="wecom_user",
                    to_user="corp_agent",
                    chat_id=DEFAULT_GROUP_ID,
                    msg_type="encrypt",
                    content="",
                )
                return build_fixed_reply(placeholder, UNSUPPORTED_MSG_REPLY)

        # 如果配置了 Token，并且企业微信传来了完整验签参数，就做 POST 签名校验。
        # 注意这里 echostr 传空字符串，因为 POST 消息验签不是 GET URL 验证。
        if self.settings.wecom_token and msg_signature and timestamp and nonce:
            if not verify_signature(
                token=self.settings.wecom_token,
                timestamp=timestamp,
                nonce=nonce,
                msg_signature=msg_signature,
                echostr="",
            ):
                logger.warning("WeCom POST signature verification failed.")
                raise HTTPException(status_code=403, detail="invalid signature")

        # 把明文 XML 解析成统一的 WecomInboundMessage。
        message = parse_plain_xml(raw_body)
        if message is None:
            # XML 解析失败时，也要返回企业微信能识别的 XML，而不是直接返回 Python 错误。
            placeholder = WecomInboundMessage(
                msg_id=f"parse-fail-{int(time.time())}",
                from_user="wecom_user",
                to_user="corp_agent",
                chat_id=DEFAULT_GROUP_ID,
                msg_type="unknown",
                content="",
            )
            return build_fixed_reply(placeholder, UNSUPPORTED_MSG_REPLY)

        # 解析成功后，真实 XML 和 Mock JSON 一样，都进入统一入站消息处理。
        return self._handle_inbound_message(message)

    def _handle_inbound_message(self, message: WecomInboundMessage) -> str:
        """统一处理一条企业微信入站消息。

        方法名前的 `_` 是 Python 约定：表示这个方法只给类内部使用。
        它不是强制 private，外部仍然能调用，但不建议这么做。

        这个方法是本文件最核心的业务流程：
        1. msg_id 去重；
        2. 过滤非文本消息；
        3. 过滤空文本；
        4. 转成 AskRequest；
        5. 调用 AskService；
        6. 把 AskResponse 转成 XML；
        7. 缓存 XML，防止重复处理。
        """

        # 第一步：按企业微信 msg_id 查缓存。
        # 如果之前处理过同一条消息，直接返回上次生成的 XML。
        # 这样可以避免企业微信重试时重复写日志、重复调用问答链路。
        cached = self.dedup_store.get_cached_xml(message.msg_id)
        if cached is not None:
            return cached

        # 目前 MVP 只支持文本消息。
        # 图片、文件、语音等类型直接返回固定“不支持”回复。
        if message.msg_type != MSG_TYPE_TEXT:
            xml_body = build_fixed_reply(message, UNSUPPORTED_MSG_REPLY)
            self.dedup_store.save_xml(message.msg_id, xml_body)
            return xml_body

        # 文本消息内容为空时，不进入 AskService。
        # 这样可以避免空问题写入 question_log。
        if not message.content:
            xml_body = build_fixed_reply(message, EMPTY_CONTENT_REPLY)
            self.dedup_store.save_xml(message.msg_id, xml_body)
            return xml_body

        # 核心转换：企业微信消息 -> 内部问答请求 AskRequest。
        #
        # 字段对应关系：
        # - question: 用户在企业微信里发的文本
        # - user_id: 企业微信发送人
        # - group_id: 企业微信群/会话 ID；没有就用默认 demo 群
        # - source_type: 固定写 wecom，后续 question_log 可以区分来源
        #
        # AskService 会继续调用 LangGraph，完成检索、命中判断、答案生成/未命中沉淀、日志落库。
        ask_response = AskService(self.session).ask(
            AskRequest(
                question=message.content,
                user_id=message.from_user,
                group_id=message.chat_id or DEFAULT_GROUP_ID,
                source_type=SOURCE_TYPE_WECOM,
            )
        )

        # 把内部 AskResponse 转成企业微信被动回复 XML。
        # 企业微信回调不能直接返回 JSON，需要返回它规定格式的 XML。
        xml_body = build_text_reply(message, ask_response)

        # 缓存本次 XML。下一次如果收到同一个 msg_id，直接返回缓存。
        self.dedup_store.save_xml(message.msg_id, xml_body)
        return xml_body
