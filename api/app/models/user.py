"""SQLAlchemy model: users (id, email, hashed_password, role, is_active). (Phase 1)"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.chat import Conversation
    from app.models.pet import ClientProfile, VetProfile


class Role(str, enum.Enum):
    """Who someone is. Self-registration may only ever create CLIENT."""

    ADMIN = "ADMIN"
    VET = "VET"
    CLIENT = "CLIENT"


class User(Base):
    """One row per login. Profile details live in client_profiles / vet_profiles."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="role", native_enum=False, length=16, validate_strings=True),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    client_profile: Mapped[ClientProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    vet_profile: Mapped[VetProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    # Phase 7. Cascades: deleting an account takes its chat history with it,
    # which is the right answer for a transcript and the wrong one for a pet --
    # see pets.py, where clinical history blocks the delete instead.
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
