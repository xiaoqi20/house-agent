from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://rentgraph:rentgraph@localhost:5433/rentgraph"
    secret_key: str = "dev-secret-change-me"
    access_token_ttl_minutes: int = 120

    llm_provider: str = "mock"  # mock | openai
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""  # 命名避开全局 OPENAI_API_KEY env 干扰

    upload_dir: Path = Path("uploads")
    max_upload_mb: int = 50
    cors_origins: list[str] = ["http://localhost:5273"]


settings = Settings()
