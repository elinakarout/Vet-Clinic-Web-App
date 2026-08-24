"""FastAPI app entrypoint: creates the app, mounts routers, configures CORS."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import appointments, auth, chat, pets, vets

app = FastAPI(title="Vet Clinic API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(pets.router)
app.include_router(pets.me_router)
app.include_router(appointments.router)
app.include_router(vets.router)
app.include_router(chat.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
