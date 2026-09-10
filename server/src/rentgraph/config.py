from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./rentgraph.db"
    secret_key: str = "dev-secret-change-me"
    access_token_ttl_minutes: int = 120

    # 临时工作台：一期数据只在本次工作台有效（PRD §1.3）
    workspace_ttl_hours: int = 72

    llm_provider: str = "mock"  # mock | openai
    llm_model: str = "qwen3.8-flash"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""  # 命名避开全局 OPENAI_API_KEY env 干扰
    llm_timeout_s: float = 120.0
    llm_max_retries: int = 1

    upload_dir: Path = Path("uploads")
    max_upload_mb: int = 50
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5273"]


settings = Settings()
