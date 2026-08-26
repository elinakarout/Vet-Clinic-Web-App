"""Reads .env into a typed Settings object, used throughout the app."""

from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # A .env is a shared file -- other tools put their own keys in it. Without
        # this, one unrelated line makes Settings() raise at import and takes
        # down the app, alembic and the whole test suite at once. Note this is
        # the opposite of the deliberate extra="forbid" on the request schemas:
        # there, an unexpected field is an attacker smuggling "role": "ADMIN";
        # here it is somebody else's config.
        #
        # **The cost is that a key spelled wrong is read by nothing, silently.**
        # Measured: a .env carrying `API_KEY=nvapi-...` instead of
        # NVIDIA_API_KEY produced no warning anywhere and a 503 on every
        # POST /chat, because no field here is named `api_key`. Only the names
        # declared below are read. tests/test_chat.py pins this behaviour so the
        # trade-off stays visible rather than being rediscovered.
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

    # Chat / LLM (Phase 7, gateway switched Phase 10) -----------------------
    # NVIDIA NIM's OpenAI-compatible endpoint. PROJECT_PLAN.md sec 7 assumed the
    # anthropic SDK and claude-opus-5; neither was ever installed -- PHASE_7.md
    # decision 1. The wire format is still the OpenAI /chat/completions shape,
    # which is what app/chat/client.py speaks.
    #
    # **One gateway, in code.** Phase 7 kept Google AI Studio and OpenRouter
    # side by side and resolved the key from this URL, so switching was three
    # .env lines. That was dropped when the project moved to NIM: pointing this
    # somewhere else now means editing chat_api_key below as well. The reason
    # for the move is quota -- OpenRouter's free tier is ~50 requests per DAY
    # across all free ids and one tool-using turn spends two to five of them,
    # which is not enough to test a booking flow through.
    chat_base_url: str = "https://integrate.api.nvidia.com/v1"
    # Chosen by measurement, not reputation -- api/.env.example carries the full
    # table and the three gates every candidate has to clear. Of eight NIM ids
    # tried, this is the only one that cleared all three: it quoted the price
    # and hours out of the knowledge base verbatim, reached propose_appointment,
    # and short-circuited the chocolate/seizures prompt without inventing a
    # phone number. It is slow (30-65s a turn) and spends a tool iteration
    # freely; openai/gpt-oss-20b is ten times faster and is the documented
    # fallback, at the cost of missing a price that is in the knowledge base.
    chat_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    # Named for the vendor, and the name matters: extra="ignore" above means a
    # key under any other name is read by nothing at all.
    nvidia_api_key: str = ""
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
    # Per user, per process. Deliberately crude; see services/ratelimit.py for
    # what this does and does not protect. It exists so a re-render loop in the
    # frontend cannot burn a day's free-tier quota before anyone notices.
    chat_rate_limit_per_minute: int = 10

    # Failed logins per minute, counted per (client address, e-mail) pair.
    # Phase 9's QA pass measured fifteen consecutive wrong passwords all
    # answering 401, so an offline guessing loop was bounded only by bcrypt.
    # Only *failures* count and a success clears the bucket, so a person who
    # mistypes twice is never locked out of their own account. Keying on the
    # pair rather than the e-mail alone matters: keying on the e-mail alone
    # lets anyone lock a known user out by guessing badly on their behalf.
    login_rate_limit_per_minute: int = 10
    # The knowledge base says "the clinic" and gives no phone number anywhere, on
    # purpose. The system prompt must not invent either, so both are settings and
    # the defaults stay vague.
    clinic_name: str = "the clinic"
    clinic_phone: str = ""

    # Render serves every domain over TLS, so the deployed frontend's origin is
    # https, not http -- an http entry here silently blocks every browser
    # request with no server-side error, since CORS rejection happens client
    # side. localhost:5173 stays in the list so `docker compose up` and the
    # non-Docker fallback keep working; production overrides this with the
    # CORS_ORIGINS env var (a JSON array, e.g. '["https://your-app.onrender.com"]')
    # rather than by editing this default.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "https://vet-clinic-web-app.onrender.com",
    ]

    @property
    def sqlalchemy_database_url(self) -> str:
        """`database_url` with the `postgres://` scheme normalised.

        SQLAlchemy's psycopg2 dialect stopped accepting the bare `postgres://`
        scheme in 1.4+; Render's managed Postgres still hands out connection
        strings written that way. Normalising once here -- rather than in both
        database.py and alembic/env.py -- keeps the two from drifting.
        """
        if self.database_url.startswith("postgres://"):
            return "postgresql://" + self.database_url[len("postgres://") :]
        return self.database_url

    @property
    def chat_api_key(self) -> str:
        """The key for the one gateway this app talks to.

        A property rather than a plain field because both readers --
        routers/chat.py's 503 check and chat/client.py's Authorization header --
        depend on the contract that an unset key is the empty string and never
        None. That empty string is what becomes a clean 503 from POST /chat
        instead of a 401 out of the provider.

        Phase 7 resolved this across two gateways by inspecting chat_base_url.
        That went away with the move to NIM (see chat_base_url above); if a
        second gateway ever comes back, this is where it goes.
        """
        return self.nvidia_api_key


def _load_settings() -> "Settings":
    """Build Settings, turning a config mistake into a sentence. (Phase 9)

    Phase 9's QA pass ran a script from the repo root instead of api/ and got a
    twelve-line pydantic traceback ending in `secret_key Field required`, which
    says nothing about the actual mistake: .env is looked up relative to the
    working directory, so nothing was found. `raise SystemExit` rather than a
    re-raise because there is no caller who can recover from this -- the process
    cannot start -- and a traceback here only buries the one line that helps.
    """
    try:
        return Settings()
    except ValidationError as exc:
        missing = [
            ".".join(str(p) for p in err["loc"])
            for err in exc.errors()
            if err["type"] == "missing"
        ]
        env_path = Path(".env").resolve()
        lines = [
            "",
            "Configuration error: this app cannot start.",
            "",
        ]
        if missing:
            lines.append(
                "  Missing required setting(s): " + ", ".join(sorted(missing))
            )
        else:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"])
                lines.append(f"  {loc}: {err['msg']}")
        lines += [
            "",
            f"  Looked for a .env file at: {env_path}"
            + ("" if env_path.exists() else "  (this file does not exist)"),
            f"  Working directory:         {Path.cwd()}",
            "",
            "  The .env path is relative to the working directory, so every",
            "  command here is run from the api/ directory. If you are in the",
            "  repository root, `cd api` first.",
            "",
            "  Starting from nothing:  cp api/.env.example api/.env",
            "  then set SECRET_KEY (python -c "
            "'import secrets; print(secrets.token_urlsafe(48))').",
            "",
        ]
        raise SystemExit("\n".join(lines)) from None


settings = _load_settings()
