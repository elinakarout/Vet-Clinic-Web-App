"""Reads .env into a typed Settings object, used throughout the app."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./data/dev.db"
    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # RFC 2606 reserves .test/.invalid/.local for documentation and testing,
    # and this project's demo data uses them throughout (admin@vetclinic.test).
    # email-validator rejects them by default. Flip this off in production.
    allow_reserved_email_domains: bool = True
    anthropic_api_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
