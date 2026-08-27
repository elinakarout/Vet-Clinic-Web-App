# Technical Handover — Vet Clinic Web App

Audience: a developer or technical lead picking up this codebase. This
document is the developer-level companion to the two client-facing guides in
this folder. It describes the system **as it exists in the repository today**,
verified directly against the code, migrations, configuration and tests.

> **A note on the AI provider:** early design intentions for this project
> called for Claude Opus via the Anthropic Python SDK. **That was never
> shipped.** The `anthropic` package was never installed, and is commented
> out of `api/requirements.txt`. The assistant actually runs against
> **NVIDIA NIM** (`nvidia/nemotron-3.5-lightning-30b-a3b`) through an
> OpenAI-compatible `/chat/completions` endpoint, which is what this document
> describes throughout.

---

## Table of contents

1. [Tech stack](#1-tech-stack)
2. [Architecture](#2-architecture)
3. [Database](#3-database)
4. [Authentication and authorization](#4-authentication-and-authorization)
5. [API surface](#5-api-surface)
6. [The AI assistant (RAG + chat)](#6-the-ai-assistant-rag--chat)
7. [Environment variables](#7-environment-variables)
8. [Docker](#8-docker)
9. [Setup (local, non-Docker)](#9-setup-local-non-docker)
10. [Deployment (Render)](#10-deployment-render)
11. [Migrations](#11-migrations)
12. [Tests](#12-tests)
13. [Project structure](#13-project-structure)
14. [Maintenance and troubleshooting](#14-maintenance-and-troubleshooting)

---

## 1. Tech stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend | React 19, Vite 8, TypeScript (strict), Tailwind CSS v4, TanStack Query 5, react-router 7 | No test runner; `tsc -b` + `oxlint` are the gates |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2 / pydantic-settings | |
| Database | SQLite (dev, `api/data/dev.db`) / PostgreSQL (production) | Same models, different `DATABASE_URL` |
| Auth | PyJWT (HS256), passlib + bcrypt | |
| Knowledge base (RAG) | ChromaDB ≥1.0,<2, bundled ONNX `all-MiniLM-L6-v2` embedder | **Not** `sentence-transformers` — deliberately, see §6 |
| AI assistant | NVIDIA NIM, OpenAI-compatible `/chat/completions`, `httpx` client | **Not** the `anthropic` SDK |
| Containerization | Docker, Docker Compose | Primary way to run the whole stack |
| Deployment target | Render (Blueprint: `render.yaml`) | Docker web service (API) + static site (frontend) + managed Postgres |

Installed package versions observed in `api/.venv` at time of writing:
`fastapi 0.141.1`, `uvicorn 0.52.4`, `pydantic 2.13.4`, `pydantic-settings
2.15.0`, `sqlalchemy 2.0.52`, `alembic 1.19.1`, `pyjwt 2.13.0`, `passlib
1.7.4`, `bcrypt 4.0.1` (pinned `<4.1`, see `requirements.txt` comment),
`chromadb 1.5.9`, `httpx 0.28.1`. None of the backend dependencies in
`requirements.txt` carry a pinned version except `pyjwt`, `bcrypt` and
`chromadb` — reinstalling from scratch may pull newer minor versions.

Frontend dependency versions are pinned with `^` ranges in
`client/package.json`: React `^19.2.8`, TanStack Query `^5.102.0`, react-router
`^7.18.2`, Tailwind `^4.3.3`, Vite `^8.2.0`, TypeScript `~6.0.2`, oxlint
`^1.75.0`.

---

## 2. Architecture

Two independent applications in one repository, talking over HTTP:

```
api/        FastAPI backend — routers/, services/, models/, schemas/, rag/, chat/
client/     React frontend (Vite) — pages/, components/, hooks/, api/, lib/
```

### Backend layering

```
routers/   HTTP only — request parsing, status codes, calling services/deps
services/  business logic, no HTTP concepts (scheduling, pets, security, ratelimit, timeutils)
models/    SQLAlchemy ORM tables
schemas/   Pydantic request/response shapes (never expose a model directly)
```

`hashed_password` lives only on the `User` model and is never serialised into
any API response — `UserOut` and every other schema simply don't declare the
field.

### Key domain rules baked into the architecture

- **The pet is the patient, the human is the client.** Medical records,
  appointments and vaccinations hang off `pets`, never off a person.
- **Profiles are separate from accounts.** `client_profiles` and
  `vet_profiles` both reference `users`, and `pets.owner_id` points at
  `client_profiles.id` — **not** `users.id`. This is the single most common
  source of off-by-one-table bugs in this codebase; the moment there is one
  admin or vet, a `users.id` and the corresponding `client_profiles.id` are
  different numbers.
- **Everything server-side is UTC; the frontend renders in clinic time.**
  `api/app/services/timeutils.py` is the only conversion point on the backend;
  `client/src/lib/datetime.ts` is the only rendering point on the frontend. The
  clinic's zone is `Asia/Beirut` by default (`clinic_timezone` /
  `VITE_CLINIC_TIMEZONE`), and the two **must** be kept in sync manually — there
  is no runtime check that they agree.

### Frontend conventions

- **Every server call goes through `client/src/api/client.ts`** —
  `apiFetch` for ordinary JSON endpoints, `apiStream` for the one
  Server-Sent-Events endpoint (`POST /chat`). Both attach the bearer token,
  normalise `{"detail": ...}` errors into a typed `ApiError`, and share the one
  global 401 handler that signs a user out (clearing TanStack Query's cache and
  the stored chat thread so the next user on that browser sees nothing of the
  previous one's).
- Server responses carry only foreign keys, never joined names —
  `AppointmentOut` has `pet_id`/`vet_id` but no pet or vet name. The frontend
  joins client-side using `usePetMap()` / `useVetMap()`.
- `ProtectedRoute` waits for an initial `bootstrapping` flag from
  `AuthProvider` before redirecting to `/login`, so a hard refresh (where the
  token exists locally but `/auth/me` hasn't answered yet) doesn't bounce a
  signed-in user out.
- Tailwind v4: theme tokens live in `@theme { ... }` inside `client/src/
  index.css`; `tailwind.config.js` is inert and has no effect — don't edit it
  expecting a result.

---

## 3. Database

11 tables, one initial Alembic migration (`ceb7d6b7c1cf_initial_tables.py`)
plus one for chat (`689ff5f47454_chat_conversations_and_messages.py`).

| Table | Purpose | Key relationships |
|---|---|---|
| `users` | One row per login: email, hashed password, `role` (`ADMIN`/`VET`/`CLIENT`), `is_active` | 1:1 with `client_profiles`/`vet_profiles` |
| `client_profiles` | Pet owner details (name, phone, address) | `user_id` → `users`; owns `pets` |
| `vet_profiles` | Clinical staff details (name, specialty, licence) | `user_id` → `users`; owns `vet_availability`, `time_off`, appointments, medical records |
| `pets` | The patient | `owner_id` → **`client_profiles.id`** (not `users.id`) |
| `vet_availability` | Recurring weekly hours (weekday 0–6, `start_time`/`end_time` as bare `Time`, `slot_minutes`) | `vet_id` → `vet_profiles` |
| `time_off` | One-off overrides (holidays, surgery blocks) | `vet_id` → `vet_profiles` |
| `appointments` | A booked slot | `pet_id` → `pets`, `vet_id` → `vet_profiles`, `created_by` → `users` (nullable) |
| `medical_records` | Clinical history | `pet_id` → `pets`, `vet_id` → `vet_profiles` (nullable) |
| `vaccinations` | Shot history + next-due date | `pet_id` → `pets` |
| `knowledge_documents` / `knowledge_chunks` | RAG source documents and their chunks | `document_id` → `knowledge_documents`; `chroma_id` links a chunk to its ChromaDB vector |
| `conversations` / `chat_messages` | Chat threads and turns | `user_id` → `users` (directly — the one place this is the correct FK, not a profile id); `conversation_id` → `conversations` |

### Constraints and indexes worth knowing

- **`uq_vet_active_slot`** — a **partial unique index** on
  `appointments(vet_id, starts_at)` restricted to
  `status IN ('REQUESTED','CONFIRMED')`. This is layer 1 of double-booking
  prevention: a cancelled appointment keeps its history row but frees the
  slot. Supported identically on SQLite and PostgreSQL via
  `sqlite_where`/`postgresql_where`.
- Cascades: deleting a `User` cascades into their profile and (for a client)
  every pet, appointment, medical record and vaccination — **but this path is
  never exercised through the API**, since there is no "delete a user" HTTP
  endpoint. Deleting a `Pet` directly is blocked in the service layer whenever
  it has any clinical history (see §5).
- Deleting a `User` also cascades their `conversations` (chat history follows
  the account; a pet's clinical history explicitly does not follow the same
  rule, and is protected instead — see `pets.py:pet_has_history`).
- `appointments.vet_id` has `ondelete="RESTRICT"` — a vet profile with any
  appointment history cannot be hard-deleted at the database level (there is
  no vet-delete endpoint either; deactivation via `is_active=False` is the
  supported way to retire staff).
- Enums (`Role`, `Sex`, `AppointmentStatus`, `SourceType`, `ChatRole`) are
  stored as `native_enum=False` strings with `validate_strings=True`, not
  native SQL enum types — chosen for SQLite/PostgreSQL portability.

### Schema-drift check

```bash
cd api && alembic revision --autogenerate -m "drift_probe"
```

On a clean tree this must produce an **empty** migration (`upgrade()` is just
`pass`). Delete the throwaway file afterwards. A non-empty result means a model
was changed without a matching migration, or a model isn't imported in
`alembic/env.py`.

---

## 4. Authentication and authorization

- **JWT, HS256**, signed with `SECRET_KEY` (no default — the app refuses to
  start without it). Access tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES`
  (default 60). There is no refresh token.
- `POST /auth/login` is the OAuth2 **password** flow — form-encoded
  (`application/x-www-form-urlencoded`), field name `username` holding the
  email — everything else in the API is JSON.
- `get_current_user` (`api/app/deps.py`) decodes the token and **re-reads the
  user row from the database on every request** — the JWT's own `role` claim
  is never trusted for authorization, only used by the frontend to render
  optimistically. This means a role change or an `is_active=False`
  deactivation takes effect immediately, not at token expiry.
- Ownership is enforced by **FastAPI dependencies**, not by helper functions a
  route author has to remember to call:
  - `get_owned_pet` — compares against `client_profile.id`; `VET`/`ADMIN`
    bypass.
  - `get_owned_appointment` — one hop further (`appointment.pet.owner_id`);
    uniquely, a `VET` is scoped to **their own** appointments only (unlike
    `get_owned_pet`, where any vet may read any patient).
  - `get_owned_conversation` — compares `conversation.user_id` directly (the
    one place `user.id` is the right FK); **no staff bypass at all** — not
    even an admin can read another user's chat transcript through the API.
- Self-registration (`POST /auth/register`) can only ever produce a `CLIENT`
  — there is no `role` field on that schema, and the schema uses
  `extra="forbid"`, so a smuggled `"role": "ADMIN"` is a `422`, not silently
  ignored.
- Staff accounts (`VET`/`ADMIN`) are created only via `POST /auth/staff`,
  itself `ADMIN`-only.
- Passwords are capped at **72 bytes** (bcrypt's own limit) and rejected above
  it with a `422`, rather than being silently truncated.
- **Rate limiting** (`api/app/services/ratelimit.py`) is a process-local,
  in-memory sliding window shared by `/auth/login` and `/chat`:
  - Login: failed attempts only, keyed by `(client IP, email)`, default 10/min,
    a success clears the bucket, answers `429` with `Retry-After`.
  - Chat: default 10 messages/minute per user.
  - This resets on process restart and is **not** shared across multiple
    uvicorn workers — real, durable rate limiting at the edge is explicitly
    out of scope here (deferred to whatever sits in front of the app in
    production).

---

## 5. API surface

Full endpoint-by-endpoint reference with request/response examples and every
status code lives in **[`API.md`](../API.md)** at the repo root, and is also
browsable live at `GET /docs` (Swagger UI) while the API is running. This
section is the map, not the detail.

| Area | Router file | Endpoints |
|---|---|---|
| Health | `main.py` | `GET /health` |
| Auth | `routers/auth.py` | `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/staff` |
| Pets | `routers/pets.py` | `GET/POST /pets`, `GET/PATCH/DELETE /pets/{id}`, `GET/PATCH /me/profile` |
| Appointments | `routers/appointments.py` | `GET /appointments/slots`, `GET/POST /appointments`, `GET /appointments/{id}`, `POST /appointments/{id}/cancel`, `POST /appointments/{id}/status` |
| Vets | `routers/vets.py` | `GET /vets`, `GET/PUT /vets/{id}/availability`, `POST /vets/{id}/time-off`, `DELETE /vets/{id}/time-off/{time_off_id}` |
| Chat | `routers/chat.py` | `POST /chat` (SSE stream), `GET /chat/conversations`, `GET/DELETE /chat/conversations/{id}` |

**Error shape** is uniform: `{"detail": "..."}` for every error except `422`,
which is FastAPI's standard validation array. `401` means "we don't know who
you are"; `403` means "we know, and the answer is no" — this distinction is
consistent everywhere in the API.

### Scheduling engine specifics (`services/scheduling.py`)

- `generate_slots` walks a vet's recurring `vet_availability`, then subtracts
  `time_off`, active appointments, and past times — by interval **overlap**,
  never by equality.
- `book_appointment` re-derives the requested slot by asking `generate_slots`
  whether it's one of the vet's own current openings, rather than
  independently re-checking hours/grid/time-off/past — one source of truth.
- Double-booking prevention is **two layers**, both required:
  1. The partial unique index `uq_vet_active_slot` (database-level).
  2. A transactional insert that catches `IntegrityError` and converts it to a
     clean `409` — never a raw `500`.
  "Check then insert" alone is a race condition; both together close it.
- The value actually stored on `starts_at` is `match.starts_at` — the instant
  `generate_slots` produced — **not** whatever the caller sent, even after
  normalisation. This matters for testing: a test that removes the UTC
  normalisation calls in `book_appointment` and its Pydantic validator will
  still pass, because storage never depended on that normalised value in the
  first place. The real invariant is "the stored value comes from the slot,
  not the request" — verify against that, not against whether a `to_utc()`
  call exists.
- `AppointmentStatus.REQUESTED` exists in the schema and the transition table
  but is **currently unreachable** — `book_appointment` always creates
  `CONFIRMED` appointments directly. This is a deliberate decision, not an
  oversight to silently "fix": the scheduling test suite encodes booking as
  always landing `CONFIRMED`, so changing this touches semantics those tests
  rely on.

---

## 6. The AI assistant (RAG + chat)

Two halves, both fully built. Summary:

### RAG (`api/app/rag/`)

Pipeline: Markdown → chunk (~800 chars) → embed → ChromaDB →
`search_knowledge(query, k=5)`. No HTTP endpoint of its own —
`chat/tools.py` wraps it as the `search_clinic_knowledge` tool.

- **Embedder:** ChromaDB's bundled ONNX `all-MiniLM-L6-v2`, **not**
  `sentence-transformers` (commented out of `requirements.txt` on purpose —
  installing it is a regression, not an upgrade; it would reintroduce the
  torch + `nvidia-*` wheel download that used to make `docker compose build
  api` fail outright).
- **Similarity floor** (`retrieval_min_score = 0.35`, measured not guessed):
  a query with no sufficiently-similar chunk returns **no passages at all**,
  which the assistant is prompted to treat as a valid "I don't know" rather
  than reciting the five least-bad matches.
- Source Markdown lives in **`api/knowledge/clinic/`** (tracked in git) —
  **not** under `api/data/`, because `.gitignore` excludes `api/data/`
  entirely and Docker Compose mounts a volume over `/app/data` that would hide
  it from the container.
- `scripts/fetch_external.py` downloads 5 allowlisted FDA pet-safety pages into
  `api/data/knowledge/external/` (derived content, not tracked). Combined
  with the 7 authored clinic documents this gives **12 documents / 117
  chunks** in the full local setup.
- `scripts/ingest_knowledge.py` rebuilds the vector store and is idempotent —
  safe to re-run at any time.

### Chat (`api/app/chat/`)

- `prompts.py` (pure — the system prompt and `EMERGENCY_SIGNS`, which is
  **derived from `knowledge/clinic/emergency-guidance.md` on purpose** — the
  two must never drift; `tests/test_chat.py` asserts they overlap) →
  `tools.py` (seven tools, built per-request as closures over the
  JWT-authenticated user) → `client.py` (the network call) → `agent.py` (the
  tool-calling loop) → `routers/chat.py` (the only importer of `agent`, and
  the only synchronous router in the app, because the tools do ordinary
  SQLAlchemy work inside the streaming generator).
- **No tool ever accepts a user id as a model-supplied parameter.** Tools
  receive resource ids (`pet_id`, `appointment_id`) and re-validate them
  through the same `get_owned_pet`/`get_owned_appointment` dependencies the
  HTTP routes use. A test asserts no tool schema exposes an identity
  parameter.
- **There is no `book_appointment` or `cancel_appointment` tool, on purpose.**
  `propose_appointment` / `propose_cancellation` return structured data the
  frontend renders as a confirm card; clicking it calls the ordinary
  `POST /appointments` / `POST /appointments/{id}/cancel` — the exact same
  code path, ownership checks and cutoff rule as manual booking.
- Only `USER` and `ASSISTANT` turns are persisted to `chat_messages` — tool
  calls and their results are not, because replaying a stale
  `find_available_slots` result on reload would offer times that may now be
  booked. `ChatMessage.payload` carries the rendered proposals instead, so a
  reload can redraw the confirm cards without re-running the model.
- **The chosen model and gateway are the product of measurement, not
  preference** — see `api/.env.example` for the full comparison table across
  eight NIM model ids and the three gates each was tested against
  (callable → emits tool calls → actually reaches `propose_appointment` while
  staying grounded in the knowledge base and never inventing details such as a
  phone number). The current pick,
  `nvidia/nemotron-3.5-lightning-30b-a3b`, is slow (30–65s/turn) but is the
  only one that cleared all three gates cleanly.
- **Gateway is not runtime-configurable any more.** `chat_base_url` and
  `chat_api_key` (which resolves to `nvidia_api_key`) are coupled in code —
  pointing at a different provider means editing `Settings.chat_api_key` in
  `config.py`, not just `.env`.
- Errors are raised **before** the SSE stream opens wherever the failure can
  be anticipated (missing key → `503`, no/bad token → `401`, wrong
  conversation owner → `403`, rate limit → `429`), so most failures are real
  HTTP status codes rather than an in-stream `error` event. Only a provider
  dying mid-reply becomes an `error` event on an already-`200` stream.

---

## 7. Environment variables

Backend (`api/.env`, loaded by `api/app/config.py`; see `api/.env.example`
for the fully annotated version):

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/dev.db` | `postgres://` is auto-normalised to `postgresql://` for SQLAlchemy |
| `SECRET_KEY` | *(none — required)* | App refuses to start without it; generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | |
| `ALLOW_RESERVED_EMAIL_DOMAINS` | `True` | Lets `*.test` demo emails validate; flip off in production |
| `CLINIC_TIMEZONE` | `Asia/Beirut` | Must match the frontend's `VITE_CLINIC_TIMEZONE` |
| `CANCELLATION_CUTOFF_HOURS` | `2` | Client-only cutoff; staff exempt |
| `MAX_SLOT_RANGE_DAYS` | `31` | Cap on `GET /appointments/slots` |
| `MAX_BOOKING_HORIZON_DAYS` | `365` | Cap on `POST /appointments` |
| `CLINIC_KNOWLEDGE_DIR` | `./knowledge/clinic` | Tracked source Markdown |
| `EXTERNAL_KNOWLEDGE_DIR` | `./data/knowledge/external` | Fetched, derived |
| `CHROMA_PATH` | `./data/chroma` | Vector store location |
| `CHROMA_COLLECTION` | `clinic_knowledge` | Must stay a cosine-space collection |
| `RETRIEVAL_K` | `5` | |
| `RETRIEVAL_MIN_SCORE` | `0.35` | Cosine similarity floor, measured — see §6 |
| `CHAT_BASE_URL` | `https://integrate.api.nvidia.com/v1` | Coupled with `chat_api_key` in code |
| `CHAT_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` | See §6 for why |
| `NVIDIA_API_KEY` | `""` (empty) | **Name must be exact** — `extra="ignore"` means any other spelling is silently read by nothing, producing a clean `503` on every `POST /chat` with no warning anywhere |
| `CHAT_MAX_TOKENS` | `2048` | |
| `CHAT_TEMPERATURE` | `0.3` | Deliberately low — a booking assistant quoting real prices should not improvise |
| `CHAT_REASONING_EFFORT` | `None` | Omitted from the request entirely when unset — not every model accepts this field |
| `CHAT_HISTORY_LIMIT` | `20` | Persisted turns, counted user+assistant together |
| `CHAT_MAX_TOOL_ITERATIONS` | `6` | Hard cap on tool-call rounds per turn |
| `CHAT_REQUEST_TIMEOUT_SECONDS` | `90.0` | |
| `CHAT_RATE_LIMIT_PER_MINUTE` | `10` | |
| `LOGIN_RATE_LIMIT_PER_MINUTE` | `10` | Failed attempts only, per (IP, email) |
| `CLINIC_NAME` | `"the clinic"` | Kept vague deliberately — the knowledge base names no phone number |
| `CLINIC_PHONE` | `""` | Empty on purpose — see §6, the "invented phone number" measurement |
| `CORS_ORIGINS` | `["http://localhost:5173", "https://vet-clinic-web-app.onrender.com"]` | JSON array; production overrides via env var, not by editing the default |

Frontend (`client/.env`, see `client/.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Always `localhost` even under Docker Compose — the **browser**, not the container, makes these calls |
| `VITE_CLINIC_TIMEZONE` | `Asia/Beirut` | Must match the backend's `CLINIC_TIMEZONE` exactly — nothing currently asserts this at runtime |

`.env` is not committed for either app; both `.env.example` files are, and are
the authoritative reference — they carry considerably more inline explanation
than this table.

---

## 8. Docker

`docker-compose.yml` at the repo root is the primary way to run the whole
stack:

```bash
docker compose up --build      # api on :8000, client on :5173
```

- The **api** service runs `sh scripts/start.sh` as its `command:` (not the
  Dockerfile's own `CMD`), which applies `alembic upgrade head` before
  `exec uvicorn`. This is deliberate: `./api:/app` is bind-mounted, so fixing
  or changing this behaviour takes effect on `docker compose up -d` with no
  image rebuild. Without this step the container serves a database with zero
  tables and 500s every real request while `/health` still reports healthy —
  `/health` never touches the database, so it proves nothing beyond "the
  process started."
- Named volumes: `api-data` (SQLite DB + Chroma store), `hf-cache`,
  `chroma-cache` (the ONNX embedder — **do not delete this** unless you're
  prepared to re-download ~80 MB on the next ingest), `client-node-modules`.
- **`./api/data/knowledge:/app/data/knowledge` is a nested bind mount**,
  declared *after* the `api-data` volume so it layers on top of it. Without
  this line the container's knowledge base silently degrades to 7 documents
  instead of 12 — nothing reports the discrepancy, so this is easy to
  reintroduce accidentally if the compose file is edited.
- The client service reads `VITE_API_URL=http://localhost:8000` — the host
  address, not the compose service name `api` — because the browser makes
  these calls from the host, not from inside the container network.
- `docker compose build api` completes in ~4.5 minutes and produces a 1.28 GB
  image. It used to fail reliably (torch wheels from
  `sentence-transformers` timing out) — that dependency is gone; see §6.

If a container-level failure looks like "everything's healthy but every
request 500s" or "the assistant answers `I don't have that` to things it
should know", check the two points above before assuming an application bug.

---

## 9. Setup (local, non-Docker)

Backend, from `api/`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # then set SECRET_KEY
alembic upgrade head                 # creates data/dev.db
python scripts/seed.py               # demo admin, 2 vets, 2 clients, 3 pets
python scripts/ingest_knowledge.py   # builds the vector store
uvicorn app.main:app --reload        # :8000, docs at /docs
```

Frontend, from `client/`:

```bash
npm install
cp .env.example .env                 # defaults usually work unchanged
npm run dev                          # :5173
```

Demo accounts (from `scripts/seed.py`, local dev only — never publish these
passwords anywhere reachable):

| Role | Email | Password |
|---|---|---|
| ADMIN | `admin@vetclinic.test` | `admin1234` |
| VET | `vet.patel@vetclinic.test` | `vet1234` |
| VET | `vet.novak@vetclinic.test` | `vet1234` |
| CLIENT | `client.jones@example.test` | `client1234` |
| CLIENT | `client.ali@example.test` | `client1234` |

`scripts/seed.py --reset` deletes these five demo users (and everything they
own) before rebuilding — the fastest way back to a clean state after manual
testing.

`scripts/fetch_external.py` downloads the 5 allowlisted FDA pages into
`api/data/knowledge/external/`. This directory is **not** committed
(`api/data/` is gitignored), so run this script once after a fresh clone if
you want the full 12-document knowledge base rather than just the 7
clinic-authored documents. It's the only script in the repo that touches the
public internet, and `fda.gov`'s `robots.txt` asks for 30 seconds between
requests, so a full run takes ~2.5 minutes.

---

## 10. Deployment (Render)

`render.yaml` at the repo root is a Render **Blueprint** — push it to GitHub,
then in the Render dashboard: **New → Blueprint → pick this repo.**

It provisions three resources in one pass:

1. **`vet-clinic-db`** — a free managed PostgreSQL database.
2. **`vet-clinic-api`** — a Docker web service built from `api/Dockerfile`.
   - `dockerCommand: sh scripts/start.sh` — **repeats the same override
     docker-compose.yml uses**, because Render doesn't read compose files and
     the Dockerfile's own `CMD` skips migrations.
   - `DATABASE_URL` is wired automatically from the managed database.
   - `SECRET_KEY` is auto-generated by Render.
   - `CORS_ORIGINS` is pre-set to the deployed frontend's origin.
   - `NVIDIA_API_KEY` is declared but **not set by the blueprint**
     (`sync: false`) — it must be entered manually in the Render dashboard
     after the first deploy.
   - `RUN_INGEST_ON_START=1` rebuilds the vector store from
     `api/knowledge/clinic/*.md` on every boot (cheap, idempotent) — but this
     does **not** run `fetch_external.py`, so a fresh Render deploy's
     knowledge base is the 7 clinic-authored documents, not the full 12,
     unless a persistent disk and an extra step are added (see the inline
     comments in `render.yaml`).
   - `SEED_ON_START=0` by default — flipping it to `1` publishes the seed
     script's well-known demo passwords to anyone who finds the URL; only use
     it for a throwaway demo deploy.
3. **`vet-clinic-web-app`** — a static site built with
   `cd client && npm ci && npm run build`, serving `client/dist`.
   - `VITE_API_URL` points at the deployed API service.
   - A catch-all rewrite (`/* → /index.html`) is required so refreshing on a
     client-side route (e.g. `/pets/3`) doesn't hit Render's static file
     server directly and 404.

Render's Blueprint schema drifts between accounts/versions — if the dashboard
flags a field as unrecognised (most likely `runtime: static` or a `plan`
value), accept the dashboard's suggested alternative and re-sync.

---

## 11. Migrations

Alembic, configured in `api/alembic.ini` / `api/alembic/env.py`. Two revisions
exist today:

1. `ceb7d6b7c1cf_initial_tables.py` — all 9 core tables (Phase 1).
2. `689ff5f47454_chat_conversations_and_messages.py` — `conversations` and
   `chat_messages` (Phase 7).

```bash
cd api
alembic upgrade head                              # apply
alembic revision --autogenerate -m "description"  # generate after a model change
```

An autogenerate on an unchanged schema **must** produce an empty migration —
that's the drift check described in §3. If a real model change produces an
empty migration instead, the new model almost certainly isn't imported in
`alembic/env.py`.

In Docker, migrations apply automatically on every container start via
`scripts/start.sh` (§8) — there is no separate manual step there.

---

## 12. Tests

Backend: `pytest -q` from `api/` (or `docker compose exec api pytest -q`).
**291 tests**, ~5 minutes (bcrypt's cost factor dominates, once per test that
logs in — not a hang):

| File | Count | Covers |
|---|---|---|
| `test_models.py` | 15 | ORM models, constraints |
| `test_auth.py` | 35 | JWT, roles, rate limiting |
| `test_pets.py` | 50 | Pet CRUD, ownership |
| `test_scheduling.py` | 91 | Slot generation, booking, double-booking, cancellation, status transitions |
| `test_rag.py` | 30 | Chunker, ChromaDB store, ingest, retrieval — fully offline (fake embedding function) |
| `test_chat.py` | 74 | Prompt, tools, streaming client, tool loop — fully offline (`httpx.MockTransport`, no real network call anywhere) |

An **autouse** fixture (`conftest.py:_reset_login_rate_limit`) resets the
process-global rate-limit dict between tests — without it, every test after
the tenth wrong password in the suite would see `429` instead of the `401` it
asserts.

Frontend has **no test runner** by design. Its gates are:

```bash
cd client
npm run build              # tsc -b (strict) then vite build — the real type gate
npm run lint                # oxlint — must be completely SILENT, not just exit 0
./scripts/verify-chat.sh    # SSE framing + clinic-time rendering, run under TZ=America/Los_Angeles on purpose
```

`verify-chat.sh` deliberately runs under a non-Beirut timezone: this repo was
written in `Asia/Beirut`, where a browser-local rendering bug produces the
*correct-looking* time by coincidence and would otherwise hide.

### Per-phase verifier subagents

`.claude/agents/phase0-verifier.md` through `phase8-verifier.md` are
Claude Code subagent definitions, each scoped to one build phase, that go
beyond `pytest` to a live round trip against a running server plus a
schema-drift check. Read-only against the repo; they only touch throwaway
databases/containers they create themselves. Run the matching one after
touching that phase's files.

### Mutation-verified guards

The project's convention is: don't trust a test until you've watched it
fail — delete or invert the guard it claims to
protect and confirm the test actually turns red. Several guards have been
verified this way — and one, notably, was **not** what it claimed to be:
`test_booking_in_a_non_utc_offset_is_stored_as_utc` passes even with both
`to_utc()` calls removed, because `book_appointment` never stores the
caller's value at all (see §5). Before relying on an existing test as proof a
change is safe, consider re-running it with the guard it claims to protect
temporarily removed.

---

## 13. Project structure

```
api/
  app/
    routers/        auth.py, pets.py, appointments.py, vets.py, chat.py
    services/        pets.py, scheduling.py, security.py, timeutils.py, ratelimit.py
    models/          user.py, pet.py, appointment.py, chat.py, knowledge.py
    schemas/         user.py, pet.py, appointment.py, chat.py
    rag/             chunker.py, store.py, ingest.py, retrieve.py
    chat/            prompts.py, tools.py, client.py, agent.py
    config.py        Settings (env-driven)
    database.py      SQLAlchemy engine/session setup
    deps.py          get_current_user, require_role, get_owned_*
    main.py          FastAPI app, router mounting, CORS, /health
  alembic/           migrations
  knowledge/clinic/  authored Markdown knowledge base (tracked in git)
  scripts/           seed.py, ingest_knowledge.py, fetch_external.py, start.sh
  tests/             pytest suite
  data/              gitignored: dev.db, chroma/, knowledge/external/
client/
  src/
    api/             client.ts (apiFetch/apiStream), pets.ts, vets.ts, appointments.ts, chat.ts
    auth/            AuthContext, ProtectedRoute, useAuth
    pages/           Dashboard, Pets, BookAppointment, Appointments, VetSchedule, Profile, Login, Register, NotFound
    components/      Layout, PetCard, PetFormDialog, AppointmentCard, SlotPicker, chat/, ui/
    hooks/           usePets, useAppointments, useVets, useProfile, useChat
    lib/             datetime.ts (the one clinic-time rendering point), cn.ts
    types/           api.ts — the TypeScript shapes matching the backend schemas
  scripts/           verify-chat.sh and its two harnesses
docker-compose.yml
render.yaml
API.md               Full HTTP endpoint reference
FRONTEND.md           Frontend design/architecture guide
```

---

## 14. Maintenance and troubleshooting

### "Everything looks healthy but every request 500s"

Check the database has actually been migrated. `GET /health` returning `{"status":
"ok"}` proves nothing beyond "the process started" — it does not touch the
database. The Docker setup runs migrations automatically on every start (see
§8), so this shouldn't recur there — but if it does:

```bash
docker compose logs -f api        # look for "[start] applying database migrations..."
```

### "The assistant answers 503 on every message"

The `NVIDIA_API_KEY` variable is either missing or misspelled in `api/.env`.
Because `Settings` uses `extra="ignore"`, a key under any other name (e.g.
`API_KEY=...`) produces **no warning anywhere** — just a clean `503`. Confirm
the exact variable name.

### "The knowledge base answers fewer questions in Docker than locally"

Confirm the nested bind mount `./api/data/knowledge:/app/data/knowledge` is
present in `docker-compose.yml` and declared **after** the `api-data` volume
line. Re-run `docker compose exec api python scripts/ingest_knowledge.py` and
check it reports 12 documents, not 7.

### "Ingest fails with a timeout downloading the embedding model"

The ~80 MB ONNX model may be partially downloaded in the `chroma-cache`
volume/directory. `scripts/ingest_knowledge.py` detects this and prints a
diagnosis distinguishing "not downloaded yet" from "partially downloaded"
(naming the file). The fastest fix on a slow network is copying a known-good
cache from a host that already has one:

```bash
docker compose cp ~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx.tar.gz \
  api:/root/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx.tar.gz
docker compose cp ~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx \
  api:/root/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx
```

### "A config script run from the repo root fails with a pydantic traceback"

`.env` is resolved relative to the **current working directory**, not the
repository root. Every backend command must be run from `api/`. `config.py`
catches this and prints a plain-language diagnosis instead of a raw pydantic
traceback, naming the exact `.env` path it looked for.

### "A port is already in use when starting fresh"

```bash
ss -ltnp | grep -E ':(8000|8001|8010|5173|5174)'
```

Beware: `pkill -f 'uvicorn app.main:app'` and `pgrep -f uvicorn` both match
**their own command line**, so a naive `pkill -f uvicorn` can kill the shell
you typed it in before the rest of your command runs. Use a bracket trick to
avoid self-matching: `pkill -f '[u]vicorn app.main:app'`.

For a full teardown, three levels are useful depending on how much you want
to erase:

- **Stop the containers, keep the database and model cache** (the usual
  answer): `docker compose down --remove-orphans`.
- **Also throw away the containerised database and knowledge base**:
  `docker compose down -v --remove-orphans` — the ~80 MB embedding model then
  re-downloads on the next ingest, which is the slowest step and the one most
  likely to time out (see the ingest-timeout section above).
- **Surgical — drop only the app's data, keep the model cache**:
  `docker compose down --remove-orphans` followed by
  `docker volume rm myfullstackweb_api-data`.

List the project's volumes with `docker volume ls | grep myfullstack`.

### Known, deliberately-unresolved gaps

These are documented decisions, not bugs to "fix" without first understanding
why they were left this way:

- `AppointmentStatus.REQUESTED` is defined but unreachable — bookings are
  always created `CONFIRMED` directly by `book_appointment`. Changing this
  touches semantics the scheduling test suite currently encodes as fixed.
- Rate limiting is process-local and resets on restart — not durable,
  not shared across workers (`config.py` comments, `services/ratelimit.py`).
- No frontend UI exists yet for creating staff accounts or editing a vet's
  weekly availability/time-off — both are reachable only via `POST
  /auth/staff` and `PUT /vets/{id}/availability` / `POST /vets/{id}/time-off`
  through `/docs`, and are documented that way in the
  [Administrator Guide](./administrator-guide.md).
- No client directory endpoint exists — staff registering a pet for a new
  client must ask the client to self-register first.
- `client/.env` doesn't exist by default; the app runs on
  `client/.env.example`'s defaults, which must stay in sync with the
  backend's `CLINIC_TIMEZONE` by hand — nothing currently asserts they agree.
