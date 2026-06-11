from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "digital-employee-assistant"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "digital_employee"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    llm_provider: str = "mock"
    llm_timeout: int = 30
    llm_max_tokens: int = 2048

    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512
    embedding_base_url: str = ""
    embedding_api_key: str = ""

    qdrant_mode: str = "local"
    qdrant_local_path: str = "./storage/qdrant"
    qdrant_collection: str = "knowledge_cards"
    qdrant_distance: str = "COSINE"

    similarity_threshold: float = 0.75
    top_k: int = 5

    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "digital-employee-assistant"
    langsmith_endpoint: str = ""
    langsmith_hide_inputs: bool = True
    langsmith_hide_outputs: bool = True

    wecom_enabled: bool = False
    wecom_mock_enabled: bool = True
    wecom_corp_id: str = ""
    wecom_agent_id: str = ""
    wecom_secret: str = ""
    wecom_token: str = ""
    wecom_encoding_aes_key: str = ""
    wecom_bot_key: str = ""
    wecom_callback_path: str = "/api/wecom/callback"
    wecom_dedup_ttl_seconds: int = 86400

    mock_mode: bool = True

    @property
    def is_mock_llm(self) -> bool:
        if self.llm_provider == "mock":
            return True
        if self.llm_provider == "deepseek" and not self.deepseek_api_key:
            return True
        return False

    @property
    def is_langsmith_enabled(self) -> bool:
        return self.langsmith_tracing and bool(self.langsmith_api_key)

    @property
    def is_wecom_enabled(self) -> bool:
        return self.wecom_enabled and bool(self.wecom_token)

    @property
    def is_mock_embedding(self) -> bool:
        return self.embedding_provider == "mock"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def health_check_url(self) -> str:
        host = "127.0.0.1" if self.app_host in {"0.0.0.0", "::"} else self.app_host
        return f"http://{host}:{self.app_port}/api/health"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
