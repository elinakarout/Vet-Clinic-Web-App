"""SQLAlchemy models: vet_availability, time_off, appointments, medical_records, vaccinations. (Phase 1)"""

from __future__ import annotations

import enum
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.pet import Pet, VetProfile
    from app.models.user import User

# Statuses that still occupy a slot. A CANCELLED or COMPLETED appointment does
# not block the vet's calendar, which is why the uniqueness index below is partial.
ACTIVE_APPOINTMENT_STATUSES = ("REQUESTED", "CONFIRMED")
_ACTIVE_STATUS_SQL = "status IN ('REQUESTED', 'CONFIRMED')"


class AppointmentStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class VetAvailability(Base):
    """Recurring weekly working hours. Mon-Fri 09:00-17:00 is five rows, not hundreds."""

    __tablename__ = "vet_availability"
    __table_args__ = (
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_availability_weekday_range"),
        CheckConstraint("slot_minutes > 0", name="ck_availability_slot_minutes_positive"),
        CheckConstraint("end_time > start_time", name="ck_availability_end_after_start"),
        Index("ix_vet_availability_vet_weekday", "vet_id", "weekday"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vet_id: Mapped[int] = mapped_column(
        ForeignKey("vet_profiles.id", ondelete="CASCADE"), nullable=False
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 = Monday .. 6 = Sunday
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")

    vet: Mapped[VetProfile] = relationship(back_populates="availability")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VetAvailability vet_id={self.vet_id} weekday={self.weekday}>"


class TimeOff(Base):
    """One-off blocks that override availability. Slot generation subtracts these."""

    __tablename__ = "time_off"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_time_off_end_after_start"),
        Index("ix_time_off_vet_starts_at", "vet_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vet_id: Mapped[int] = mapped_column(
        ForeignKey("vet_profiles.id", ondelete="CASCADE"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200))

    vet: Mapped[VetProfile] = relationship(back_populates="time_off")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<TimeOff vet_id={self.vet_id} {self.starts_at}..{self.ends_at}>"


class Appointment(Base):
    """A booked slot. Layer 1 of double-booking prevention is the partial unique index."""

    __tablename__ = "appointments"
    __table_args__ = (
        # Layer 1: the database itself refuses a second *active* booking on the same
        # vet + start time. Partial, so a cancelled slot can be rebooked without
        # losing the cancelled row. Supported by both SQLite and PostgreSQL.
        Index(
            "uq_vet_active_slot",
            "vet_id",
            "starts_at",
            unique=True,
            sqlite_where=text(_ACTIVE_STATUS_SQL),
            postgresql_where=text(_ACTIVE_STATUS_SQL),
        ),
        CheckConstraint("ends_at > starts_at", name="ck_appointments_end_after_start"),
        Index("ix_appointments_vet_starts_at", "vet_id", "starts_at"),
        Index("ix_appointments_pet_starts_at", "pet_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), nullable=False)
    vet_id: Mapped[int] = mapped_column(
        ForeignKey("vet_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(
            AppointmentStatus,
            name="appointment_status",
            native_enum=False,
            length=16,
            validate_strings=True,
        ),
        nullable=False,
        default=AppointmentStatus.CONFIRMED,
        server_default=AppointmentStatus.CONFIRMED.value,
    )
    # Which *user* booked it: tells a self-service booking from a receptionist one.
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    pet: Mapped[Pet] = relationship(back_populates="appointments")
    vet: Mapped[VetProfile] = relationship(back_populates="appointments")
    creator: Mapped[User | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Appointment id={self.id} vet_id={self.vet_id} {self.starts_at} {self.status}>"


class MedicalRecord(Base):
    """Clinical history. Hangs off the pet (the patient), never off a human."""

    __tablename__ = "medical_records"
    __table_args__ = (Index("ix_medical_records_pet_visit_date", "pet_id", "visit_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), nullable=False)
    vet_id: Mapped[int | None] = mapped_column(ForeignKey("vet_profiles.id", ondelete="SET NULL"))
    visit_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    treatment: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    pet: Mapped[Pet] = relationship(back_populates="medical_records")
    vet: Mapped[VetProfile | None] = relationship(back_populates="medical_records")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MedicalRecord id={self.id} pet_id={self.pet_id} {self.visit_date}>"


class Vaccination(Base):
    """Shot history, with the date the next dose falls due."""

    __tablename__ = "vaccinations"
    __table_args__ = (Index("ix_vaccinations_pet_due_at", "pet_id", "due_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), nullable=False)
    vaccine_name: Mapped[str] = mapped_column(String(120), nullable=False)
    given_at: Mapped[date] = mapped_column(Date, nullable=False)
    due_at: Mapped[date | None] = mapped_column(Date)

    pet: Mapped[Pet] = relationship(back_populates="vaccinations")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Vaccination id={self.id} pet_id={self.pet_id} {self.vaccine_name!r}>"
