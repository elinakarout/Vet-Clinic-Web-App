"""SQLAlchemy models: client_profiles, vet_profiles, pets. (Phase 1)"""

from __future__ import annotations

import enum
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import User

if TYPE_CHECKING:
    from app.models.appointment import (
        Appointment,
        MedicalRecord,
        TimeOff,
        Vaccination,
        VetAvailability,
    )


class Sex(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    UNKNOWN = "UNKNOWN"


class ClientProfile(Base):
    """The human who owns pets. Pets hang off *this* table, not off users."""

    __tablename__ = "client_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="client_profile")
    pets: Mapped[list[Pet]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ClientProfile id={self.id} name={self.full_name!r}>"


class VetProfile(Base):
    """A member of clinical staff. Appointments and availability reference this id."""

    __tablename__ = "vet_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(120))
    license_no: Mapped[str | None] = mapped_column(String(60), unique=True)

    user: Mapped[User] = relationship(back_populates="vet_profile")
    availability: Mapped[list[VetAvailability]] = relationship(
        back_populates="vet", cascade="all, delete-orphan", passive_deletes=True
    )
    time_off: Mapped[list[TimeOff]] = relationship(
        back_populates="vet", cascade="all, delete-orphan", passive_deletes=True
    )
    appointments: Mapped[list[Appointment]] = relationship(back_populates="vet")
    medical_records: Mapped[list[MedicalRecord]] = relationship(back_populates="vet")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VetProfile id={self.id} name={self.full_name!r}>"


class Pet(Base):
    """The patient. owner_id references client_profiles.id, NOT users.id."""

    __tablename__ = "pets"
    __table_args__ = (
        CheckConstraint("weight_kg IS NULL OR weight_kg >= 0", name="ck_pets_weight_non_negative"),
        Index("ix_pets_owner_id", "owner_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    species: Mapped[str] = mapped_column(String(40), nullable=False)
    breed: Mapped[str | None] = mapped_column(String(80))
    sex: Mapped[Sex] = mapped_column(
        SAEnum(Sex, name="sex", native_enum=False, length=16, validate_strings=True),
        nullable=False,
        default=Sex.UNKNOWN,
        server_default=Sex.UNKNOWN.value,
    )
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[ClientProfile] = relationship(back_populates="pets")
    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="pet", cascade="all, delete-orphan", passive_deletes=True
    )
    medical_records: Mapped[list[MedicalRecord]] = relationship(
        back_populates="pet", cascade="all, delete-orphan", passive_deletes=True
    )
    vaccinations: Mapped[list[Vaccination]] = relationship(
        back_populates="pet", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Pet id={self.id} name={self.name!r} owner_id={self.owner_id}>"
