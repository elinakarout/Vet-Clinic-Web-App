"""Reads .env into a typed Settings object, used throughout the app."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./data/dev.db"
    secret_key: str
    anthropic_api_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
