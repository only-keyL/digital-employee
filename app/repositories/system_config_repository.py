"""系统配置项数据访问层。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.system_config import SystemConfig
from app.repositories.base_repository import BaseRepository


class SystemConfigRepository(BaseRepository[SystemConfig]):
    """system_config 表读写，用于持久化运行时配置快照。"""

    def __init__(self, session: Session) -> None:
        super().__init__(session, SystemConfig)

    def get_by_key(self, config_key: str) -> SystemConfig | None:
        """按配置键查询。"""
        stmt = select(SystemConfig).where(SystemConfig.config_key == config_key)
        return self.session.scalars(stmt).first()

    def upsert_defaults(self) -> int:
        """将 settings 中的默认值写入库（仅插入缺失项），返回新增条数。"""
        defaults = [
            ("embedding_provider", settings.embedding_provider, "Embedding provider"),
            ("embedding_model", settings.embedding_model, "Embedding model"),
            ("embedding_dimension", str(settings.embedding_dimension), "Embedding dimension"),
            ("qdrant_collection", settings.qdrant_collection, "Qdrant collection name"),
            ("similarity_threshold", str(settings.similarity_threshold), "Similarity threshold"),
            ("top_k", str(settings.top_k), "Top K retrieval count"),
            ("llm_provider", settings.llm_provider, "LLM provider"),
            ("llm_model", settings.deepseek_model, "LLM model name"),
        ]

        inserted = 0
        for key, value, description in defaults:
            existing = self.get_by_key(key)
            if existing is None:
                self.session.add(
                    SystemConfig(
                        config_key=key,
                        config_value=value,
                        description=description,
                    )
                )
                inserted += 1
        return inserted
