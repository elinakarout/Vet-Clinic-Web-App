"""Every SQLAlchemy model, re-exported.

Import this module (not the individual files) anywhere the full set of tables
must be registered on ``Base.metadata`` -- alembic/env.py and tests/conftest.py
both rely on it. A missing import here is why ``alembic revision --autogenerate``
produces an empty migration.
"""

from app.models.appointment import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentStatus,
    MedicalRecord,
    TimeOff,
    Vaccination,
    VetAvailability,
)
from app.models.chat import ChatMessage, ChatRole, Conversation
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, SourceType
from app.models.pet import ClientProfile, Pet, Sex, VetProfile
from app.models.user import Role, User

__all__ = [
    "ACTIVE_APPOINTMENT_STATUSES",
    "Appointment",
    "AppointmentStatus",
    "ChatMessage",
    "ChatRole",
    "ClientProfile",
    "Conversation",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "MedicalRecord",
    "Pet",
    "Role",
    "Sex",
    "SourceType",
    "TimeOff",
    "User",
    "Vaccination",
    "VetAvailability",
    "VetProfile",
]
