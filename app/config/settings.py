from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从环境变量与 .env 加载。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 应用基础 ---
    app_name: str = "digital-employee-assistant"  # 应用名称
    app_env: str = "mvpdocs"  # 运行环境
    app_host: str = "0.0.0.0"  # 监听地址
    app_port: int = 8000  # 监听端口
    app_debug: bool = True  # 调试模式

    # --- MySQL ---
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "root"
    mysql_database: str = "digital_employee"

    # --- LLM（DeepSeek / Mock）---
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    llm_provider: str = "mock"  # mock | deepseek
    llm_timeout: int = 30
    llm_max_tokens: int = 2048

    # --- Embedding ---
    embedding_provider: str = "fastembed"  # mock | fastembed
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512
    embedding_base_url: str = ""
    embedding_api_key: str = ""

    # --- Qdrant 向量库 ---
    qdrant_mode: str = "local"  # local | remote
    qdrant_local_path: str = "./storage/qdrant"
    qdrant_collection: str = "knowledge_cards"
    qdrant_distance: str = "COSINE"

    # --- RAG 检索参数 ---
    similarity_threshold: float = 0.75  # 相似度阈值
    top_k: int = 5  # 召回条数

    # --- LangSmith 观测 ---
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "digital-employee-assistant"
    langsmith_endpoint: str = ""
    langsmith_hide_inputs: bool = True
    langsmith_hide_outputs: bool = True

    # --- 企业微信 ---
    wecom_enabled: bool = False  # 是否启用真实回调
    wecom_mock_enabled: bool = True  # 是否启用 Mock 回调
    wecom_corp_id: str = ""
    wecom_agent_id: str = ""
    wecom_secret: str = ""
    wecom_token: str = ""
    wecom_encoding_aes_key: str = ""
    wecom_bot_key: str = ""
    wecom_callback_path: str = "/api/wecom/callback"
    wecom_dedup_ttl_seconds: int = 86400  # 消息去重 TTL（秒）

    mock_mode: bool = True  # 全局 Mock 演示模式

    @property
    def is_mock_llm(self) -> bool:
        """是否使用 Mock LLM（显式 mock 或未配置 DeepSeek Key）。"""
        if self.llm_provider == "mock":
            return True
        if self.llm_provider == "deepseek" and not self.deepseek_api_key:
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
    def database_url(self) -> str:
        """SQLAlchemy MySQL 连接 URL。"""
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


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例（带缓存）。"""
    return Settings()


settings = get_settings()
