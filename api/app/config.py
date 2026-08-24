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

    # Chat / LLM (Phase 7) -------------------------------------------------
    # Google AI Studio's OpenAI-compatible endpoint. PROJECT_PLAN.md sec 7 assumed
    # the anthropic SDK and claude-opus-5; this project runs on Gemini instead --
    # see PHASE_7.md decision 1. The gateway is a setting rather than a literal
    # because OpenRouter speaks the identical /chat/completions schema, so moving
    # between the two is these three lines and no code at all.
    chat_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    # gemini-3.5-flash, not the newer 3.7: the free tier caps 3.7-flash at
    # **20 requests per day** (measured, PHASE_7.md), and one tool-using chat
    # turn costs two to four of them. 3.5-flash has a far larger daily allowance
    # and throttles at 5/minute instead. The quota is per-model, so changing this
    # line gets a fresh bucket.
    chat_model: str = "gemini-3.5-flash"
    # Two names for the same slot, because the two gateways issue different keys
    # and .env should not have to be rewritten to switch. Resolution order is in
    # the chat_api_key property below. Note that until these were declared,
    # extra="ignore" above meant an OPENROUTER_API_KEY line in .env was read by
    # nothing at all.
    google_ai_studio_api_key: str = ""
    openrouter_api_key: str = ""
    chat_max_tokens: int = 2048
    # Low, not zero. This is a booking assistant quoting prices and policy out of
    # a knowledge base; invention is the failure mode, not dullness.
    chat_temperature: float = 0.3
    # None means the field is omitted from the request entirely. Not every model
    # behind an OpenAI-compatible gateway accepts reasoning_effort, and sending it
    # to one that does not is a 400 rather than a graceful ignore.
    chat_reasoning_effort: str | None = None
    # PROJECT_PLAN.md sec 7 "Cost and latency": cap history so a long chat does not
    # grow unboundedly. Counted in persisted turns, user and assistant alike.
    chat_history_limit: int = 20
    # How many times the model may call tools and be asked again within one turn.
    # "look up the pet, check the schedule, find slots, propose" is four, so this
    # leaves room without letting a confused model loop until the bill notices.
    chat_max_tool_iterations: int = 6
    chat_request_timeout_seconds: float = 90.0
    # Per user, per process. Deliberately crude -- Phase 9 owns real rate
    # limiting; this exists so a re-render loop in the frontend cannot burn a
    # day's free-tier quota before anyone notices.
    chat_rate_limit_per_minute: int = 10
    # The knowledge base says "the clinic" and gives no phone number anywhere, on
    # purpose. The system prompt must not invent either, so both are settings and
    # the defaults stay vague.
    clinic_name: str = "the clinic"
    clinic_phone: str = ""

    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def chat_api_key(self) -> str:
        """The key for whichever gateway chat_base_url points at.

        Google AI Studio first because that is the default base URL. Falling
        through to OpenRouter means a .env that already has one key works without
        being edited -- and an empty string here is what routers/chat.py turns
        into a clean 503 instead of a 401 from the provider.
        """
        return self.google_ai_studio_api_key or self.openrouter_api_key


settings = Settings()
