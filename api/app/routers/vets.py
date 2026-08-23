"""GET /vets, GET/PUT /vets/{id}/availability, time-off. (Phase 4)

The other half of scheduling: before a client can pick a slot, someone has to say
when the vet works. PROJECT_PLAN.md lists these paths under vets.py; the admin UI
that drives them is Phase 9.

Who may write here is a two-step rule -- an ADMIN may edit any vet's calendar, a
VET may edit only their own, and a CLIENT may edit none. `_may_manage` is the one
place that decides it.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Role, TimeOff, User, VetAvailability, VetProfile
from app.schemas.appointment import (
    AvailabilityIn,
    AvailabilityOut,
    TimeOffCreate,
    TimeOffOut,
    VetAvailabilityOut,
)
from app.schemas.user import VetOut
from app.services.timeutils import CLINIC_TZ, now_utc

router = APIRouter(prefix="/vets", tags=["vets"])

_UNPROCESSABLE = 422


def _get_vet(db: Session, vet_id: int) -> VetProfile:
    vet = db.get(VetProfile, vet_id)
    if vet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vet not found")
    return vet


def _may_manage(vet: VetProfile, user: User) -> None:
    """403 unless the caller is an admin, or this vet editing their own calendar.

    A VET is compared on vet_profile.id, not user.id -- every vet foreign key in
    the schema points at vet_profiles, and the two id sequences drift apart the
    moment the clinic has one admin.
    """
    if user.role is Role.ADMIN:
        return
    if user.role is Role.VET:
        profile = user.vet_profile
        if profile is not None and profile.id == vet.id:
            return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


@router.get("", response_model=list[VetOut])
def list_vets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[VetOut]:
    """The vets a client can book with.

    Deactivated accounts are filtered out rather than deleted: PHASE_1.md keeps a
    departed vet's row so their appointment history survives (vet_id is ON DELETE
    RESTRICT). They simply stop being offered.
    """
    stmt = (
        select(VetProfile)
        .join(User, VetProfile.user_id == User.id)
        .where(User.is_active.is_(True))
        .order_by(VetProfile.full_name, VetProfile.id)
    )
    return [VetOut.from_profile(vet) for vet in db.scalars(stmt)]


@router.get("/{vet_id}/availability", response_model=VetAvailabilityOut)
def read_availability(
    vet_id: int,
    days: int = Query(default=60, ge=1, le=365, description="How far ahead to list time off"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VetAvailabilityOut:
    """A vet's weekly hours, plus the upcoming blocks that override them.

    Both halves in one response because neither answers "when does this vet work"
    on its own. `timezone` is echoed back so the frontend does not have to hard-code
    what the bare 09:00 in `start_time` means.
    """
    vet = _get_vet(db, vet_id)

    weekly = db.scalars(
        select(VetAvailability)
        .where(VetAvailability.vet_id == vet.id)
        .order_by(VetAvailability.weekday, VetAvailability.start_time)
    ).all()

    horizon = now_utc() + timedelta(days=days)
    upcoming = db.scalars(
        select(TimeOff)
        .where(TimeOff.vet_id == vet.id, TimeOff.ends_at > now_utc(), TimeOff.starts_at < horizon)
        .order_by(TimeOff.starts_at)
    ).all()

    return VetAvailabilityOut(
        vet_id=vet.id,
        timezone=str(CLINIC_TZ),
        availability=[AvailabilityOut.model_validate(row) for row in weekly],
        time_off=[TimeOffOut.model_validate(row) for row in upcoming],
    )


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _reject_overlaps(blocks: list[AvailabilityIn]) -> None:
    """422 if two blocks on the same weekday overlap.

    This is what keeps a vet's slot grid unambiguous, and it matters more than it
    looks. uq_vet_active_slot is keyed on an *exact* starts_at, so two overlapping
    availability rows with different slot_minutes would generate slots that
    collide in real time while looking distinct to the index -- a 45-minute
    booking at 10:00 and a 30-minute one at 10:30. Refusing the overlap at the
    source is cheaper than detecting the collision at booking time.
    """
    by_weekday: dict[int, list[AvailabilityIn]] = {}
    for block in blocks:
        by_weekday.setdefault(block.weekday, []).append(block)

    for weekday, day_blocks in by_weekday.items():
        ordered = sorted(day_blocks, key=lambda b: b.start_time)
        for earlier, later in zip(ordered, ordered[1:]):
            if later.start_time < earlier.end_time:
                raise HTTPException(
                    _UNPROCESSABLE,
                    f"Overlapping availability blocks on weekday {weekday}",
                )


@router.put("/{vet_id}/availability", response_model=list[AvailabilityOut])
def replace_availability(
    vet_id: int,
    blocks: list[AvailabilityIn],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AvailabilityOut]:
    """Replace a vet's whole working week.

    PUT rather than PATCH on purpose: a week is edited as a whole. Dropping
    Friday means deleting a row, and a partial merge would leave "this vet no
    longer works Fridays" inexpressible. An empty list is legal and means exactly
    that -- a vet with no bookable hours, which is what you want while someone is
    on long-term leave.

    Existing appointments are **not** touched. Narrowing hours does not cancel
    anything already booked outside them; a clinic honours a commitment it made,
    and cancelling by side effect of an admin edit is the wrong default. Those
    appointments simply stop being re-bookable.
    """
    vet = _get_vet(db, vet_id)
    _may_manage(vet, current_user)
    _reject_overlaps(blocks)

    existing = db.scalars(
        select(VetAvailability).where(VetAvailability.vet_id == vet.id)
    ).all()
    for row in existing:
        db.delete(row)
    db.flush()

    created = [
        VetAvailability(
            vet_id=vet.id,
            weekday=block.weekday,
            start_time=block.start_time,
            end_time=block.end_time,
            slot_minutes=block.slot_minutes,
        )
        for block in blocks
    ]
    db.add_all(created)
    db.commit()

    refreshed = db.scalars(
        select(VetAvailability)
        .where(VetAvailability.vet_id == vet.id)
        .order_by(VetAvailability.weekday, VetAvailability.start_time)
    ).all()
    return [AvailabilityOut.model_validate(row) for row in refreshed]


@router.post(
    "/{vet_id}/time-off", response_model=TimeOffOut, status_code=status.HTTP_201_CREATED
)
def create_time_off(
    vet_id: int,
    payload: TimeOffCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TimeOffOut:
    """Block out a span -- a holiday, a surgery list, lunch.

    Slot generation subtracts these, so this is how a vet takes a morning off
    without editing their recurring hours. Appointments already booked inside the
    block are left alone, for the same reason narrowing availability does not
    cancel anything: staff cancel those deliberately, one at a time.
    """
    vet = _get_vet(db, vet_id)
    _may_manage(vet, current_user)

    block = TimeOff(
        vet_id=vet.id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        reason=payload.reason,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return TimeOffOut.model_validate(block)


@router.delete("/{vet_id}/time-off/{time_off_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_off(
    vet_id: int,
    time_off_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Remove a time-off block, making those slots bookable again."""
    vet = _get_vet(db, vet_id)
    _may_manage(vet, current_user)

    block = db.get(TimeOff, time_off_id)
    # The vet_id check is not redundant with the path: without it, a vet could
    # delete a colleague's block by naming their own id in the path and any
    # time_off id in the tail. 404 rather than 403 -- as far as this vet's
    # calendar is concerned, that block does not exist.
    if block is None or block.vet_id != vet.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Time off not found")

    db.delete(block)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
