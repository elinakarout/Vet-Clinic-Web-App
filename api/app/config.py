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
    # Scheduling (Phase 4) -------------------------------------------------
    # vet_availability.start_time/end_time are bare Time columns with no zone.
    # They are read as *clinic-local* wall clock, so "09:00" stays 09:00 through
    # a DST change instead of drifting an hour twice a year. Every datetime that
    # reaches the database is converted to UTC first (see services/timeutils.py).
    clinic_timezone: str = "Asia/Beirut"
    # A CLIENT may not cancel inside this many hours of the start. VET and ADMIN
    # are exempt -- the rule is clinic policy towards clients, and staff need to
    # cancel a same-day appointment when someone phones in.
    cancellation_cutoff_hours: int = 2
    # Caps on GET /appointments/slots and POST /appointments respectively, so one
    # request cannot ask the server to walk ten years of availability.
    max_slot_range_days: int = 31
    max_booking_horizon_days: int = 365

    anthropic_api_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
