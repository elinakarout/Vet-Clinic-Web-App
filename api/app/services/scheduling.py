"""generate_slots, book_appointment, cancel_appointment -- the scheduling engine. (Phase 4)

The heart of the app, and the one module where getting it subtly wrong is
invisible until two clients hold the same slot.

Nothing here raises HTTPException or knows what a status code is (CLAUDE.md's
layering rule, and the shape PROJECT_PLAN.md sketches for book()). It raises the
domain errors below and routers/appointments.py maps them onto 404/409/422.

Every datetime crossing this module is normalised through services/timeutils.py
before it is compared or stored. That is not housekeeping: SQLite discards the
offset on write, so an un-normalised aware datetime walks straight past the
uq_vet_active_slot unique index. See the module docstring there.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentStatus,
    Pet,
    Role,
    TimeOff,
    User,
    VetAvailability,
    VetProfile,
)
from app.services.timeutils import CLINIC_TZ, ensure_utc, local_to_utc, now_utc, to_utc

# ---------------------------------------------------------------------------
# Domain errors. The router owns the mapping to HTTP; this module owns the rules.
# ---------------------------------------------------------------------------


class SchedulingError(Exception):
    """Base for everything this module refuses to do."""


class VetNotFound(SchedulingError):
    """No such vet, or their account is deactivated."""


class SlotUnavailable(SchedulingError):
    """The requested time is not a bookable slot on that vet's calendar.

    Covers every reason at once -- outside working hours, off the slot grid, in
    a time-off block, in the past, or already taken at check time. Deliberately
    one error rather than five: the caller's next move is identical in all of
    them (ask for the slot list again), and enumerating the reasons tells an
    unauthenticated prober more about the clinic's calendar than it needs.
    """


class SlotTaken(SchedulingError):
    """Someone else booked it between our check and our insert. Layer 2."""


class PetAlreadyBooked(SchedulingError):
    """That pet already has an appointment overlapping this time."""


class BookingTooFarAhead(SchedulingError):
    """Beyond max_booking_horizon_days."""


class CancellationRefused(SchedulingError):
    """Too late, already over, or already in a terminal status."""


class InvalidTransition(SchedulingError):
    """Not a legal move on the status graph."""


# ---------------------------------------------------------------------------
# Slot generation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Slot:
    """One bookable opening. Both datetimes are aware UTC."""

    starts_at: datetime
    ends_at: datetime
    vet_id: int
    slot_minutes: int


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open interval overlap: [a) and [b) share time.

    Touching intervals do not overlap -- an appointment ending at 10:00 leaves
    10:00 free, which is the whole premise of a back-to-back slot grid.
    """
    return a_start < b_end and a_end > b_start


def _busy_intervals(
    db: Session,
    *,
    vet_id: int,
    window_start: datetime,
    window_end: datetime,
    ignore_appointment_id: int | None = None,
) -> list[tuple[datetime, datetime]]:
    """Every span in the window where this vet cannot see a patient.

    Two bulk queries for the whole date range, not one per candidate slot. The
    window is deliberately generous (a day either side); exact filtering happens
    per-slot against these intervals in Python.
    """
    off_stmt = select(TimeOff.starts_at, TimeOff.ends_at).where(
        TimeOff.vet_id == vet_id,
        TimeOff.starts_at < window_end,
        TimeOff.ends_at > window_start,
    )

    appt_stmt = select(Appointment.starts_at, Appointment.ends_at).where(
        Appointment.vet_id == vet_id,
        # The strings live in models/appointment.py next to the partial index
        # that uses them. Re-spelling them here is how the two drift apart.
        Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        Appointment.starts_at < window_end,
        Appointment.ends_at > window_start,
    )
    if ignore_appointment_id is not None:
        appt_stmt = appt_stmt.where(Appointment.id != ignore_appointment_id)

    rows = list(db.execute(off_stmt)) + list(db.execute(appt_stmt))
    # ensure_utc because SQLite hands these back naive and they are about to be
    # compared against aware slot boundaries.
    return [(ensure_utc(start), ensure_utc(end)) for start, end in rows]


def vet_is_bookable(db: Session, vet_id: int) -> VetProfile:
    """The vet profile, if appointments may be made against it.

    A deactivated user keeps their vet_profile row -- PHASE_1.md is explicit that
    a vet with booked appointments is deactivated rather than deleted, and
    appointments.vet_id is ON DELETE RESTRICT to enforce it. So existence of the
    profile is not enough; the account behind it has to still be live.
    """
    vet = db.get(VetProfile, vet_id)
    if vet is None or vet.user is None or not vet.user.is_active:
        raise VetNotFound("Vet not found")
    return vet


def generate_slots(
    db: Session,
    *,
    vet_id: int,
    date_from: date,
    date_to: date,
    now: datetime | None = None,
) -> list[Slot]:
    """Free openings for one vet, over a range of **clinic-local** dates.

    date_from/date_to are dates on the clinic's wall clock, because that is what
    a client means by "Tuesday". Every Slot that comes back is aware UTC.

    The order of the filters is the order PROJECT_PLAN.md Phase 4 lists them:
    walk availability, then subtract time-off, booked appointments and the past.
    """
    vet_is_bookable(db, vet_id)
    now = ensure_utc(now) if now is not None else now_utc()

    availability = db.scalars(
        select(VetAvailability)
        .where(VetAvailability.vet_id == vet_id)
        .order_by(VetAvailability.weekday, VetAvailability.start_time)
    ).all()
    if not availability:
        return []

    by_weekday: dict[int, list[VetAvailability]] = {}
    for row in availability:
        by_weekday.setdefault(row.weekday, []).append(row)

    # A generous UTC prefilter for the bulk queries. Not computed with
    # local_to_utc: midnight is exactly the local time Asia/Beirut skips on the
    # spring-forward day, so asking for it would return None on that one date.
    window_start = datetime.combine(date_from, time.min, tzinfo=timezone.utc) - timedelta(days=1)
    window_end = datetime.combine(date_to, time.min, tzinfo=timezone.utc) + timedelta(days=2)
    busy = _busy_intervals(
        db, vet_id=vet_id, window_start=window_start, window_end=window_end
    )

    slots: list[Slot] = []
    day = date_from
    while day <= date_to:
        # date.weekday() is already 0=Monday..6=Sunday, matching the column.
        for row in by_weekday.get(day.weekday(), []):
            step = timedelta(minutes=row.slot_minutes)
            cursor = datetime.combine(day, row.start_time)
            closing = datetime.combine(day, row.end_time)
            while cursor + step <= closing:
                # A slot whose *end* would pass closing time is not offered: a
                # 45-minute vet working to 18:00 gets no 17:45 appointment.
                starts_at = local_to_utc(day, cursor.time())
                cursor += step
                if starts_at is None:
                    continue  # a local time the DST change skipped
                ends_at = starts_at + step
                if starts_at < now:
                    continue
                if any(_overlaps(starts_at, ends_at, b_start, b_end) for b_start, b_end in busy):
                    continue
                slots.append(
                    Slot(
                        starts_at=starts_at,
                        ends_at=ends_at,
                        vet_id=vet_id,
                        slot_minutes=row.slot_minutes,
                    )
                )
        day += timedelta(days=1)

    slots.sort(key=lambda s: s.starts_at)
    return slots


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


def _pet_is_busy(db: Session, *, pet_id: int, starts_at: datetime, ends_at: datetime) -> bool:
    """True if this pet is already booked over that span, with any vet.

    uq_vet_active_slot is keyed on the *vet*, so nothing in the database stops
    Biscuit being booked with two vets at once. A pet cannot be in two consulting
    rooms, and an owner who has double-booked by accident wants to hear about it.
    """
    rows = db.execute(
        select(Appointment.starts_at, Appointment.ends_at).where(
            Appointment.pet_id == pet_id,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        )
    )
    return any(
        _overlaps(starts_at, ends_at, ensure_utc(s), ensure_utc(e)) for s, e in rows
    )


def book_appointment(
    db: Session,
    *,
    pet: Pet,
    vet_id: int,
    starts_at: datetime,
    reason: str | None,
    created_by: int | None,
) -> Appointment:
    """Book a slot, or raise. Both layers of double-booking prevention.

    `pet` is a row the caller has already been proven to own -- it arrives from
    Depends(get_owned_pet), so this function never has to decide who may book for
    whom.
    """
    # First, before any comparison or query. An aware datetime in another zone
    # would otherwise be stored as its own wall clock and slip past the unique
    # index entirely -- measured, see services/timeutils.py.
    starts_at = to_utc(starts_at)

    vet_is_bookable(db, vet_id)

    horizon = now_utc() + timedelta(days=settings.max_booking_horizon_days)
    if starts_at > horizon:
        raise BookingTooFarAhead(
            f"Cannot book more than {settings.max_booking_horizon_days} days ahead"
        )

    # One rule instead of five. Asking the generator "is this one of yours?"
    # settles working hours, grid alignment, time-off, the past and existing
    # bookings in a single place, so the check can never disagree with the list
    # the client was shown.
    local_day = starts_at.astimezone(CLINIC_TZ).date()
    match = next(
        (
            slot
            for slot in generate_slots(db, vet_id=vet_id, date_from=local_day, date_to=local_day)
            if slot.starts_at == starts_at
        ),
        None,
    )
    if match is None:
        raise SlotUnavailable("That time is not available")

    if _pet_is_busy(db, pet_id=pet.id, starts_at=match.starts_at, ends_at=match.ends_at):
        raise PetAlreadyBooked("That pet already has an appointment at this time")

    appointment = Appointment(
        pet_id=pet.id,
        vet_id=vet_id,
        starts_at=match.starts_at,
        ends_at=match.ends_at,
        reason=reason,
        status=AppointmentStatus.CONFIRMED,
        created_by=created_by,
    )
    db.add(appointment)
    try:
        db.commit()
    except IntegrityError:
        # Layer 2. The check above is not a substitute for this: between it and
        # the insert, another request can slip in. Never a 500.
        db.rollback()
        raise SlotTaken("That time was just booked. Please pick another.") from None
    db.refresh(appointment)
    return appointment


# ---------------------------------------------------------------------------
# Cancelling and status
# ---------------------------------------------------------------------------

_TERMINAL = (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED)

# Re-confirming a cancelled appointment would try to re-occupy a slot another
# client may now hold, so the terminal states really are terminal.
_LEGAL_TRANSITIONS: dict[AppointmentStatus, frozenset[AppointmentStatus]] = {
    AppointmentStatus.REQUESTED: frozenset(
        {AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED}
    ),
    AppointmentStatus.CONFIRMED: frozenset(
        {AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED}
    ),
    AppointmentStatus.CANCELLED: frozenset(),
    AppointmentStatus.COMPLETED: frozenset(),
}


def cancel_appointment(db: Session, *, appointment: Appointment, user: User) -> Appointment:
    """Cancel, freeing the slot. Who may call this is already settled upstream.

    deps.get_owned_appointment has proven the caller is the owning client, the
    assigned vet, or an admin. What is left is *when*: a client is held to the
    clinic's cutoff, staff are not.
    """
    if appointment.status in _TERMINAL:
        raise CancellationRefused(
            f"Appointment is already {appointment.status.value.lower()}"
        )

    starts_at = ensure_utc(appointment.starts_at)
    now = now_utc()
    if starts_at <= now:
        raise CancellationRefused("Appointment has already started")

    if user.role is Role.CLIENT:
        cutoff = timedelta(hours=settings.cancellation_cutoff_hours)
        if starts_at - now < cutoff:
            raise CancellationRefused(
                f"Appointments cannot be cancelled within "
                f"{settings.cancellation_cutoff_hours} hours of the start. "
                f"Please call the clinic."
            )

    # Not a delete: the row is history, and the partial index means a CANCELLED
    # row stops occupying the slot the moment the status changes.
    appointment.status = AppointmentStatus.CANCELLED
    db.commit()
    db.refresh(appointment)
    return appointment


def set_appointment_status(
    db: Session, *, appointment: Appointment, new_status: AppointmentStatus
) -> Appointment:
    """Move an appointment along the status graph. Staff only, enforced upstream."""
    current = appointment.status
    if new_status == current:
        raise InvalidTransition(f"Appointment is already {current.value.lower()}")
    if new_status not in _LEGAL_TRANSITIONS[current]:
        raise InvalidTransition(
            f"Cannot change status from {current.value} to {new_status.value}"
        )

    appointment.status = new_status
    try:
        db.commit()
    except IntegrityError:
        # REQUESTED -> CONFIRMED keeps the slot occupied, so it cannot collide.
        # Guarded anyway: a status route that grows a new transition should get a
        # 409 rather than a 500 the day it does.
        db.rollback()
        raise SlotTaken("That time is no longer free.") from None
    db.refresh(appointment)
    return appointment


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------


def appointments_visible_to(
    user: User,
    *,
    pet_id: int | None = None,
    vet_id: int | None = None,
    status: AppointmentStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Select:
    """The SELECT a given user is allowed to run over appointments.

    Same contract as services/pets.py:pets_visible_to -- returns the statement so
    the router applies limit/offset, and a filter argument can only ever narrow.
    A CLIENT passing vet_id sees their own appointments with that vet, never
    somebody else's: widening a scope through a query parameter is privilege
    escalation wearing a filter's clothes.

    A VET is scoped to their own schedule here. That is deliberately stricter
    than pets, where any vet may read any patient: clinical need justifies seeing
    a patient's record, not reading a colleague's diary. ADMIN sees everything.
    """
    stmt = select(Appointment)

    if user.role is Role.CLIENT:
        profile = user.client_profile
        # -1 matches nothing rather than raising, so a client with no profile row
        # gets an empty list instead of a 500.
        owner_id = profile.id if profile is not None else -1
        stmt = stmt.join(Pet, Appointment.pet_id == Pet.id).where(Pet.owner_id == owner_id)
        if vet_id is not None:
            stmt = stmt.where(Appointment.vet_id == vet_id)
    elif user.role is Role.VET:
        profile = user.vet_profile
        stmt = stmt.where(Appointment.vet_id == (profile.id if profile is not None else -1))
    elif vet_id is not None:
        stmt = stmt.where(Appointment.vet_id == vet_id)

    if pet_id is not None:
        stmt = stmt.where(Appointment.pet_id == pet_id)
    if status is not None:
        stmt = stmt.where(Appointment.status == status)
    if date_from is not None:
        stmt = stmt.where(Appointment.starts_at >= to_utc(date_from))
    if date_to is not None:
        stmt = stmt.where(Appointment.starts_at < to_utc(date_to))

    return stmt.order_by(Appointment.starts_at, Appointment.id)
