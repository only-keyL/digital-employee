"""应用配置兼容入口：转发至 app.core.settings，避免 MVP 代码大量改动。"""

from app.core.settings import Settings, get_settings, load_settings_from_env_file, settings

__all__ = ["Settings", "get_settings", "load_settings_from_env_file", "settings"]
