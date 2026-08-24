"""Reads .env into a typed Settings object, used throughout the app."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # A .env is a shared file -- other tools put their own keys in it. Without
        # this, one unrelated line (an OPENROUTER_API_KEY, say) makes Settings()
        # raise at import and takes down the app, alembic and the whole test
        # suite at once. Note this is the opposite of the deliberate
        # extra="forbid" on the request schemas: there, an unexpected field is an
        # attacker smuggling "role": "ADMIN"; here it is somebody else's config.
        extra="ignore",
    )

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

    # RAG / knowledge base (Phase 6) ---------------------------------------
    # Authored clinic Markdown is tracked source, so it lives OUTSIDE data/:
    # .gitignore excludes api/data/, and docker-compose mounts the api-data
    # volume over /app/data, which would hide it from the container entirely.
    # Fetched text and the vector store are derived, and stay under data/.
    # Paths are relative to the CWD the app runs from (api/), like database_url.
    clinic_knowledge_dir: str = "./knowledge/clinic"
    external_knowledge_dir: str = "./data/knowledge/external"
    chroma_path: str = "./data/chroma"
    chroma_collection: str = "clinic_knowledge"
    retrieval_k: int = 5
    # Cosine similarity floor. Below this a passage is dropped, so a nonsense
    # query returns [] rather than the five least-bad chunks. Measured, not
    # guessed: over 12 in-domain and 10 out-of-domain queries against the real
    # store, in-domain top-1 scored 0.501-0.773 and out-of-domain 0.071-0.262.
    # 0.35 sits inside that gap, 0.09 above the worst false positive and 0.15
    # below the weakest true one. Re-measure if the knowledge base changes
    # shape -- PHASE_6.md records the numbers and the script that produced them.
    retrieval_min_score: float = 0.35

    anthropic_api_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
