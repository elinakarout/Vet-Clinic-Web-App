"""Pydantic schemas: AppointmentCreate, AppointmentOut, SlotOut. (Phase 4)

Mirrors models/appointment.py, which holds all three scheduling tables, so the
availability and time-off shapes live here too rather than in a fourth module.

**Every datetime in this file is UTC, in and out.** Incoming values are
normalised (an offset the client chose is honoured, then converted); outgoing
values carry an explicit `+00:00` rather than the bare naive string SQLite hands
back. That second half also settles the ambiguity PHASE_2.md flagged, where
`created_at` serialised with no offset at all while every document claimed the
API spoke UTC.
"""

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.models import AppointmentStatus
from app.services.timeutils import ensure_utc, to_utc


class _UtcModel(BaseModel):
    """Serialises every datetime field as aware UTC.

    SQLite returns naive datetimes even from a DateTime(timezone=True) column, so
    without this an appointment comes back as "2026-09-01T09:00:00" and the
    frontend has to guess the zone. It guesses local, and the booking shows up
    hours out.
    """

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("starts_at", "ends_at", check_fields=False)
    def _serialise_utc(self, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------


class SlotOut(_UtcModel):
    """One free opening. What the Phase 5 SlotPicker renders."""

    starts_at: datetime
    ends_at: datetime
    vet_id: int
    slot_minutes: int


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------


class AppointmentCreate(BaseModel):
    """Book a slot.

    `starts_at` must be an exact slot boundary from GET /appointments/slots.
    There is no `ends_at`: the length comes from the vet's `slot_minutes`, so a
    caller cannot ask for a two-hour consultation by widening the window.

    There is no `status` either -- booking always produces CONFIRMED. A field
    that accepts exactly one value is the trap PHASE_2.md describes for
    ClientRegister.role, so it does not exist and extra="forbid" makes sending
    one a 422.
    """

    model_config = ConfigDict(extra="forbid")

    pet_id: int = Field(gt=0)
    vet_id: int = Field(gt=0)
    starts_at: datetime
    reason: str | None = Field(default=None, max_length=300)

    @field_validator("starts_at")
    @classmethod
    def _require_offset(cls, value: datetime) -> datetime:
        """Reject a naive datetime outright, then normalise to UTC.

        A naive "2026-09-01T09:00:00" is ambiguous by exactly the amount that
        matters here -- two or three hours, depending on the season. Guessing
        would book someone into the wrong slot silently; a 422 asks the caller to
        say what they meant. `2026-09-01T09:00:00Z` and `...T12:00:00+03:00` are
        both accepted and are the same instant.
        """
        if value.tzinfo is None:
            raise ValueError(
                "starts_at must include a UTC offset, e.g. 2026-09-01T09:00:00Z"
            )
        return to_utc(value)


class AppointmentOut(_UtcModel):
    """An appointment as the API describes it."""

    id: int
    pet_id: int
    vet_id: int
    starts_at: datetime
    ends_at: datetime
    reason: str | None = None
    status: AppointmentStatus
    created_by: int | None = None


class AppointmentStatusUpdate(BaseModel):
    """Staff moving an appointment along the status graph.

    CANCELLED is accepted here but the dedicated /cancel route is the one clients
    reach; this exists so an admin correcting a mistake has one endpoint rather
    than two half-overlapping ones.
    """

    model_config = ConfigDict(extra="forbid")

    status: AppointmentStatus


# ---------------------------------------------------------------------------
# Availability and time off
# ---------------------------------------------------------------------------


class AvailabilityIn(BaseModel):
    """One recurring weekly block. Times are the clinic's **local** wall clock.

    Unlike everything else in this file these are not UTC, and that is the point:
    a vet works 09:00 to 17:00 in Beirut all year, and storing 07:00Z would make
    them start an hour late every summer. See services/timeutils.py.
    """

    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6, description="0 = Monday .. 6 = Sunday")
    start_time: time
    end_time: time
    # Mirrors ck_availability_slot_minutes_positive. The upper bound is not in
    # the database; it is here so a typo'd 3000 is a 422 rather than a vet with
    # exactly one two-day appointment slot.
    slot_minutes: int = Field(default=30, ge=5, le=480)

    @model_validator(mode="after")
    def _end_after_start(self) -> "AvailabilityIn":
        # Mirrors ck_availability_end_after_start, so a bad row is a 422 from
        # pydantic rather than an IntegrityError-shaped 500 from the driver.
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.slot_minutes > _minutes_between(self.start_time, self.end_time):
            raise ValueError("slot_minutes is longer than the working block")
        return self


def _minutes_between(start: time, end: time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


class AvailabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vet_id: int
    weekday: int
    start_time: time
    end_time: time
    slot_minutes: int


class TimeOffCreate(_UtcModel):
    """A one-off block that overrides availability. UTC, like every instant."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    starts_at: datetime
    ends_at: datetime
    reason: str | None = Field(default=None, max_length=200)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("time-off datetimes must include a UTC offset")
        return to_utc(value)

    @model_validator(mode="after")
    def _end_after_start(self) -> "TimeOffCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class TimeOffOut(_UtcModel):
    id: int
    vet_id: int
    starts_at: datetime
    ends_at: datetime
    reason: str | None = None


class VetAvailabilityOut(BaseModel):
    """GET /vets/{id}/availability -- the weekly grid plus what overrides it.

    One response rather than two endpoints because they are never useful apart:
    "when does this vet work" is only answerable with both halves.
    """

    vet_id: int
    timezone: str
    availability: list[AvailabilityOut]
    time_off: list[TimeOffOut]
