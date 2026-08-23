"""GET /appointments/slots, POST /appointments, GET /appointments, cancel, status. (Phase 4)

HTTP only. Every rule about *when* an appointment may exist lives in
services/scheduling.py; this file's job is to turn a request into a call, and a
domain error into a status code.

Every route reaches an existing appointment through Depends(get_owned_appointment)
and an existing pet through Depends(get_owned_pet). There is no second path to
either row in this file, which is the point.
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user, get_owned_appointment, get_owned_pet
from app.models import Appointment, AppointmentStatus, Role, User
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentStatusUpdate,
    SlotOut,
)
from app.services import scheduling
from app.services.scheduling import (
    BookingTooFarAhead,
    CancellationRefused,
    InvalidTransition,
    PetAlreadyBooked,
    SlotTaken,
    SlotUnavailable,
    VetNotFound,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])

# Not status.HTTP_422_UNPROCESSABLE_ENTITY: starlette renamed it to
# ..._UNPROCESSABLE_CONTENT and deprecated the old spelling, and the new one does
# not exist on the older starlette in api/Dockerfile's image. The number is the
# one thing both versions agree on.
_UNPROCESSABLE = 422


# ---------------------------------------------------------------------------
# Free slots
#
# Declared before /{appointment_id}: FastAPI matches in definition order, so the
# other way round "slots" is parsed as an id and this route becomes unreachable.
# ---------------------------------------------------------------------------


@router.get("/slots", response_model=list[SlotOut])
def list_slots(
    vet_id: int = Query(gt=0),
    date_from: date = Query(description="Clinic-local date, inclusive"),
    date_to: date = Query(description="Clinic-local date, inclusive"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SlotOut]:
    """Free openings for one vet over a range of clinic-local dates.

    The dates are the clinic's, not the caller's: a client asking for "Tuesday"
    means Tuesday in Beirut regardless of where they are reading the page from.
    Everything that comes back is UTC.
    """
    if date_to < date_from:
        raise HTTPException(_UNPROCESSABLE, "date_to cannot be before date_from")
    span = (date_to - date_from).days + 1
    if span > settings.max_slot_range_days:
        raise HTTPException(
            _UNPROCESSABLE,
            f"Date range cannot exceed {settings.max_slot_range_days} days",
        )

    try:
        slots = scheduling.generate_slots(db, vet_id=vet_id, date_from=date_from, date_to=date_to)
    except VetNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    return [SlotOut.model_validate(slot) for slot in slots]


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentOut:
    """Book a slot.

    The pet is fetched through get_owned_pet, so a client booking somebody else's
    pet is a 403 before any scheduling logic runs. Staff bypass that check, which
    is how a receptionist books a walk-in.
    """
    # get_owned_pet is a dependency taking pet_id from the path; here the id
    # arrives in the body, so it is called directly with the same arguments
    # FastAPI would have supplied. Same function, same 404/403 -- calling it
    # rather than reimplementing the check is the whole reason it exists.
    pet = get_owned_pet(pet_id=payload.pet_id, current_user=current_user, db=db)

    try:
        appointment = scheduling.book_appointment(
            db,
            pet=pet,
            vet_id=payload.vet_id,
            starts_at=payload.starts_at,
            reason=payload.reason,
            # Which *user* booked it -- a client for themselves, or a
            # receptionist on their behalf. Phase 7's chatbot reads this.
            created_by=current_user.id,
        )
    except VetNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except BookingTooFarAhead as exc:
        raise HTTPException(_UNPROCESSABLE, str(exc)) from None
    except (SlotUnavailable, SlotTaken, PetAlreadyBooked) as exc:
        # 409, never 500. PROJECT_PLAN.md Phase 4's verification step is exactly
        # this: two curl calls for one slot, one 201 and one clean conflict.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    return AppointmentOut.model_validate(appointment)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    pet_id: int | None = Query(default=None, gt=0),
    vet_id: int | None = Query(default=None, gt=0),
    appointment_status: AppointmentStatus | None = Query(default=None, alias="status"),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AppointmentOut]:
    """A client's own appointments; a vet's own schedule; everything, for an admin.

    Every filter can only narrow. A client passing `vet_id` sees their own
    appointments with that vet, never somebody else's -- the same rule
    services/pets.py applies to `owner_id`, for the same reason.
    """
    stmt = (
        scheduling.appointments_visible_to(
            current_user,
            pet_id=pet_id,
            vet_id=vet_id,
            status=appointment_status,
            date_from=date_from,
            date_to=date_to,
        )
        .limit(limit)
        .offset(offset)
    )
    return [AppointmentOut.model_validate(row) for row in db.scalars(stmt)]


@router.get("/{appointment_id}", response_model=AppointmentOut)
def read_appointment(
    appointment: Appointment = Depends(get_owned_appointment),
) -> AppointmentOut:
    """404 if there is no such appointment, 403 if it is not yours."""
    return AppointmentOut.model_validate(appointment)


# ---------------------------------------------------------------------------
# Changing one
# ---------------------------------------------------------------------------


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel(
    appointment: Appointment = Depends(get_owned_appointment),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentOut:
    """Cancel, freeing the slot for someone else.

    Returns the updated appointment rather than a 204: the frontend has a card on
    screen whose status just changed, and a body saves it a second request.

    A CLIENT is held to the clinic's cancellation cutoff; the assigned vet and an
    admin are not, because a same-day cancellation phoned in to reception has to
    be actionable by the person who answered the phone.
    """
    try:
        updated = scheduling.cancel_appointment(db, appointment=appointment, user=current_user)
    except CancellationRefused as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return AppointmentOut.model_validate(updated)


@router.post("/{appointment_id}/status", response_model=AppointmentOut)
def update_status(
    payload: AppointmentStatusUpdate,
    appointment: Appointment = Depends(get_owned_appointment),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentOut:
    """Move an appointment along the status graph. Staff only.

    get_owned_appointment has already scoped a VET to their own schedule, so a
    vet cannot mark a colleague's consultation complete. The role check here is
    what stops a CLIENT self-confirming or marking their own visit COMPLETED.
    """
    if current_user.role is Role.CLIENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")

    try:
        updated = scheduling.set_appointment_status(
            db, appointment=appointment, new_status=payload.status
        )
    except (InvalidTransition, SlotTaken) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return AppointmentOut.model_validate(updated)
