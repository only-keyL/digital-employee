"""统一应用配置：从环境变量与 .env 加载，兼容 MVP 既有字段与二期新增字段。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOWED_APP_ENVS = frozenset({"dev", "test", "prod"})


class Settings(BaseSettings):
    """应用配置类，集中管理运行环境、数据库、LLM、向量库、Redis、LangSmith、企微等配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- 基础运行配置 ---
    app_name: str = Field(default="digital-employee-assistant", description="应用名称")
    app_env: str = Field(default="dev", description="运行环境，仅允许 dev / test / prod")
    app_host: str = Field(default="0.0.0.0", description="HTTP 服务监听地址")
    app_port: int = Field(default=8000, description="HTTP 服务监听端口")
    app_debug: bool = Field(
        default=True,
        validation_alias=AliasChoices("APP_DEBUG", "DEBUG"),
        description="调试模式开关",
    )

    # --- 数据库（支持 DATABASE_URL 或拆分 MySQL 配置）---
    database_url_override: str = Field(
        default="",
        validation_alias="DATABASE_URL",
        description="完整数据库连接 URL，设置后优先于拆分 MySQL 字段",
    )
    mysql_host: str = Field(default="127.0.0.1", description="MySQL 主机")
    mysql_port: int = Field(default=3306, description="MySQL 端口")
    mysql_user: str = Field(default="root", description="MySQL 用户名")
    mysql_password: str = Field(default="root", description="MySQL 密码")
    mysql_database: str = Field(default="digital_employee", description="MySQL 数据库名")

    # --- LLM（本阶段仅配置字段，MVP 仍使用 deepseek_* 与 llm_provider）---
    llm_provider: str = Field(default="mock", description="LLM 提供方：mock / deepseek 等")
    llm_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("LLM_BASE_URL", "DEEPSEEK_BASE_URL"),
        description="LLM API 基础地址",
    )
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "DEEPSEEK_API_KEY"),
        description="LLM API Key",
    )
    llm_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias=AliasChoices("LLM_MODEL", "DEEPSEEK_MODEL"),
        description="LLM 模型名称",
    )
    llm_timeout: int = Field(
        default=30,
        validation_alias=AliasChoices("LLM_TIMEOUT", "LLM_TIMEOUT_SECONDS"),
        description="LLM 请求超时（秒）",
    )
    llm_max_tokens: int = Field(default=2048, description="LLM 最大输出 token 数")
    llm_max_retries: int = Field(default=2, description="LLM 请求最大重试次数")
    llm_temperature: float = Field(default=0.2, description="LLM 采样温度")

    # --- Embedding（MVP 既有字段 + Stage3 扩展）---
    embedding_provider: str = Field(default="fastembed", description="Embedding 提供方")
    embedding_model: str = Field(default="BAAI/bge-small-zh-v1.5", description="Embedding 模型")
    embedding_dimension: int = Field(
        default=512,
        validation_alias=AliasChoices("EMBEDDING_DIMENSION", "EMBEDDING_VECTOR_SIZE"),
        description="Embedding 向量维度",
    )
    embedding_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("EMBEDDING_BASE_URL",),
        description="Embedding API 地址",
    )
    embedding_api_key: str = Field(default="", description="Embedding API Key")
    embedding_timeout_seconds: int = Field(default=15, description="Embedding 请求超时（秒）")
    embedding_max_retries: int = Field(default=2, description="Embedding 最大重试次数")
    rag_high_confidence_threshold: float = Field(default=0.78, description="RAG 高置信度阈值")

    # --- Qdrant / 向量检索（本阶段仅配置字段）---
    vector_provider: str = Field(default="qdrant", description="向量库提供方")
    qdrant_mode: str = Field(default="local", description="Qdrant 模式：local / remote")
    qdrant_deployment: str = Field(default="cloud", description="Qdrant 部署形态")
    qdrant_local_path: str = Field(default="./storage/qdrant", description="本地 Qdrant 存储路径")
    qdrant_url: str = Field(default="", description="远程 Qdrant 服务地址")
    qdrant_api_key: str = Field(default="", description="Qdrant API Key")
    qdrant_collection: str = Field(default="knowledge_cards", description="Qdrant 集合名称")
    qdrant_rag_collection: str = Field(
        default="",
        validation_alias=AliasChoices("QDRANT_RAG_COLLECTION"),
        description="Stage3 RAG 专用 collection（为空则使用 {qdrant_collection}_rag）",
    )
    qdrant_distance: str = Field(default="COSINE", description="向量距离度量")
    qdrant_timeout_seconds: int = Field(default=5, description="Qdrant 请求超时（秒）")
    top_k: int = Field(
        default=5,
        validation_alias=AliasChoices("TOP_K", "QDRANT_TOP_K"),
        description="向量检索 Top K",
    )
    similarity_threshold: float = Field(
        default=0.75,
        validation_alias=AliasChoices("SIMILARITY_THRESHOLD", "QDRANT_SCORE_THRESHOLD"),
        description="向量检索相似度阈值",
    )

    # --- Redis（本阶段仅配置字段）---
    redis_url: str = Field(default="", description="Redis 连接 URL")
    wecom_dedup_ttl_seconds: int = Field(default=86400, description="企微消息去重 TTL（秒）")
    deposit_session_ttl_seconds: int = Field(default=600, description="指令式知识沉淀会话 TTL（秒）")

    # --- LangSmith（本阶段仅配置字段）---
    langsmith_tracing: bool = Field(default=False, description="是否启用 LangSmith 追踪")
    langsmith_api_key: str = Field(default="", description="LangSmith API Key")
    langsmith_project: str = Field(
        default="digital-employee-assistant",
        description="LangSmith 项目名称",
    )
    langsmith_endpoint: str = Field(default="", description="LangSmith 自定义 Endpoint")
    langsmith_hide_inputs: bool = Field(default=True, description="LangSmith 是否隐藏输入")
    langsmith_hide_outputs: bool = Field(default=True, description="LangSmith 是否隐藏输出")

    # --- 企业微信（本阶段仅配置字段）---
    wecom_enabled: bool = Field(default=False, description="是否启用真实企微回调")
    wecom_mock_enabled: bool = Field(default=True, description="是否启用企微 Mock 入口")
    wecom_corp_id: str = Field(default="", description="企微 CorpID")
    wecom_agent_id: str = Field(default="", description="企微 AgentID")
    wecom_secret: str = Field(default="", description="企微 Secret")
    wecom_token: str = Field(default="", description="企微回调 Token")
    wecom_encoding_aes_key: str = Field(default="", description="企微回调 EncodingAESKey")
    wecom_bot_key: str = Field(default="", description="企微机器人 Key")
    wecom_callback_path: str = Field(default="/api/wecom/callback", description="企微回调路径")
    wecom_callback_url: str = Field(default="", description="企微回调完整 URL")

    mock_mode: bool = Field(default=True, description="全局 Mock 演示模式")

    # --- 阶段 6：后台鉴权 / 消息幂等 / 安全扫描 / 运维 ---
    admin_auth_enabled: bool = Field(default=False, description="是否启用后台 Token 鉴权")
    admin_token: str = Field(default="", description="后台管理 Token，禁止打印明文")
    admin_token_header: str = Field(default="X-Admin-Token", description="后台 Token 请求头名称")
    message_dedup_enabled: bool = Field(default=True, description="是否启用 message_id 幂等")
    message_dedup_ttl_seconds: int = Field(default=86400, description="消息幂等记录 TTL 建议值（秒）")
    security_scan_fail_on_secret: bool = Field(default=True, description="安全扫描发现泄露时是否失败")
    security_scan_exclude_dirs: str = Field(
        default=".git,.venv,__pycache__,docs/prod",
        description="安全扫描排除目录，逗号分隔",
    )
    ops_max_retry_tasks: int = Field(default=50, description="运维脚本单次最大重试任务数")

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        """限制 APP_ENV 只能为 dev / test / prod。"""
        normalized = value.strip().lower()
        if normalized not in _ALLOWED_APP_ENVS:
            allowed = "、".join(sorted(_ALLOWED_APP_ENVS))
            raise ValueError(f"APP_ENV 只允许 {allowed}，当前为: {value}")
        return normalized

    @model_validator(mode="after")
    def sync_legacy_llm_fields(self) -> Settings:
        """保持 deepseek_* 与 llm_* 字段读写一致，避免 MVP 代码改动。"""
        return self

    @property
    def deepseek_api_key(self) -> str:
        """兼容 MVP：DeepSeek API Key 与 LLM_API_KEY 同源。"""
        return self.llm_api_key

    @property
    def deepseek_base_url(self) -> str:
        """兼容 MVP：DeepSeek Base URL。"""
        return self.llm_base_url

    @property
    def deepseek_model(self) -> str:
        """兼容 MVP：DeepSeek 模型名。"""
        return self.llm_model

    @property
    def is_dev(self) -> bool:
        """是否为本地开发环境。"""
        return self.app_env == "dev"

    @property
    def is_test(self) -> bool:
        """是否为测试环境。"""
        return self.app_env == "test"

    @property
    def is_prod(self) -> bool:
        """是否为生产环境。"""
        return self.app_env == "prod"

    @property
    def is_mock_llm(self) -> bool:
        """是否使用 Mock LLM（显式 mock 或未配置 LLM Key）。"""
        if self.llm_provider == "mock":
            return True
        if self.llm_provider == "deepseek" and not self.llm_api_key:
            return True
        return False

    @property
    def is_langsmith_enabled(self) -> bool:
        """LangSmith 追踪是否可用（开关开启且已配置 API Key）。"""
        return self.langsmith_tracing and bool(self.langsmith_api_key)

    @property
    def is_wecom_enabled(self) -> bool:
        """企业微信真实回调是否可用（开关开启且已配置 Token）。"""
        return self.wecom_enabled and bool(self.wecom_token)

    @property
    def is_mock_embedding(self) -> bool:
        """是否使用 Mock Embedding。"""
        return self.embedding_provider == "mock"

    @property
    def effective_qdrant_rag_collection(self) -> str:
        """Stage3 RAG 使用的 Qdrant collection，与阶段 2 探测 collection 隔离。"""
        name = (self.qdrant_rag_collection or "").strip()
        if name:
            return name
        base = (self.qdrant_collection or "knowledge_cards").strip()
        return f"{base}_rag"

    @property
    def effective_mysql_user(self) -> str:
        """从 DATABASE_URL 或拆分配置解析实际数据库用户名，供 prod 校验使用。"""
        if self.database_url_override:
            parsed = urlparse(self._normalize_database_url(self.database_url_override))
            return (parsed.username or "").strip()
        return self.mysql_user.strip()

    @property
    def effective_mysql_database(self) -> str:
        """从 DATABASE_URL 或拆分配置解析实际数据库名。"""
        if self.database_url_override:
            parsed = urlparse(self._normalize_database_url(self.database_url_override))
            db_name = (parsed.path or "").lstrip("/")
            return db_name.split("?")[0] if db_name else ""
        return self.mysql_database.strip()

    @property
    def database_url(self) -> str:
        """SQLAlchemy MySQL 连接 URL。"""
        if self.database_url_override:
            return self.database_url_override
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def health_check_url(self) -> str:
        """本机健康检查 URL（供脚本使用）。"""
        host = "127.0.0.1" if self.app_host in {"0.0.0.0", "::"} else self.app_host
        return f"http://{host}:{self.app_port}/api/health"

    @staticmethod
    def _normalize_database_url(url: str) -> str:
        """将 SQLAlchemy 风格 URL 转为 urlparse 可解析格式。"""
        if url.startswith("mysql+pymysql://"):
            return "mysql://" + url[len("mysql+pymysql://") :]
        return url


def _build_settings_class(env_file: str | None = None) -> type[Settings]:
    """按指定 env 文件动态构造 Settings 类，供脚本校验使用。"""
    if not env_file:
        return Settings

    class _FileSettings(Settings):
        model_config = SettingsConfigDict(
            env_file=env_file,
            env_file_encoding="utf-8",
            extra="ignore",
            populate_by_name=True,
        )

    return _FileSettings


def load_settings_from_env_file(
    env_file: str,
    app_env: str | None = None,
    **overrides: Any,
) -> Settings:
    """从指定 env 文件加载配置；仅读取指定文件，不合并项目根 .env。"""
    from dotenv import dotenv_values

    path = Path(env_file)
    if not path.is_file():
        raise FileNotFoundError(f"配置文件不存在：{env_file}")

    # 先用 dotenv 校验解析，再交给 pydantic-settings 按字段别名映射
    dotenv_values(path)

    settings_cls = _build_settings_class(str(path))
    payload: dict[str, Any] = dict(overrides)
    if app_env is not None:
        payload["app_env"] = app_env
    return settings_cls(**payload)


def apply_env_file(env_file: str) -> Settings:
    """将 env 文件加载到进程环境并刷新全局 Settings 缓存（供 prod 脚本使用）。"""
    from dotenv import load_dotenv

    path = Path(env_file)
    if not path.is_file():
        raise FileNotFoundError(f"配置文件不存在：{env_file}")
    load_dotenv(path, override=True)
    get_settings.cache_clear()
    return get_settings()


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例（带缓存）。"""
    return Settings()


settings = get_settings()
