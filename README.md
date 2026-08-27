# Vet Clinic Web App

A veterinary clinic platform: role-based accounts for clinic staff and pet
owners, pet records, appointment scheduling, and an AI assistant that answers
questions from a clinic knowledge base and proposes appointments you confirm
with one click.

**Live demo:** [vet-clinic-web-app.onrender.com](https://vet-clinic-web-app.onrender.com)
— register your own account to try it (the deployed instance doesn't publish
demo passwords). It's hosted on Render's free tier, so the first request after
a period of inactivity can take up to a minute while the backend wakes up.

## Stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript, Tailwind, TanStack Query |
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Database | SQLite in development → PostgreSQL in production |
| Knowledge base | ChromaDB with its bundled ONNX `all-MiniLM-L6-v2` embedder (local, no torch) |
| Assistant | NVIDIA NIM, via an OpenAI-compatible chat endpoint, with tool use |

## What you can do in the app

Register as a pet owner, add your pets, browse a vet's free slots for the
week, book, and cancel. Vets get their own schedule and can confirm and
complete visits. Admins see the whole clinic. A chat assistant is available on
every page for general questions and for proposing (never auto-booking)
appointments. Light and dark themes.

## Running it

```bash
docker compose up --build          # api on :8000, client on :5173
docker compose exec api python scripts/seed.py             # demo accounts
docker compose exec api python scripts/ingest_knowledge.py # knowledge base
```

Or without Docker:

```bash
# Backend — from api/
source .venv/bin/activate
alembic upgrade head               # create data/dev.db
python scripts/seed.py             # demo admin, 2 vets, 2 clients, 3 pets
uvicorn app.main:app --reload      # API on :8000, interactive docs at /docs

# Frontend — from client/
npm run dev                        # UI on :5173
```

Both apps read their configuration from `.env` files — copy `api/.env.example`
and `client/.env.example` and fill in `SECRET_KEY` at minimum. The chat
assistant needs one extra line, a free [NVIDIA NIM](https://build.nvidia.com)
key as `NVIDIA_API_KEY` — without it the app runs normally and the assistant
answers a clean "unavailable" instead of a chat reply.

## Documentation

Full documentation lives in **[`docs/`](./docs/)**:

- **[`docs/client-user-manual.md`](./docs/client-user-manual.md)** — for pet
  owners using the app.
- **[`docs/administrator-guide.md`](./docs/administrator-guide.md)** — for
  clinic staff (vets and admins) running the clinic day to day.
- **[`docs/technical-handover.md`](./docs/technical-handover.md)** — for
  developers: architecture, database schema, the API, environment variables,
  Docker/deployment, migrations, and tests.

While the API is running, interactive endpoint documentation is also always
available at `http://localhost:8000/docs`.
