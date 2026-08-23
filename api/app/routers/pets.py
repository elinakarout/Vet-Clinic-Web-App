"""GET/POST /pets, GET/PATCH/DELETE /pets/{id}, GET/PATCH /me/profile. (Phase 3)

Two routers in one module because /me/profile does not sit under /pets but is
the same unit of work: the things a signed-in human owns.

Every pet endpoint below reaches its pet through `Depends(get_owned_pet)`. That
is the whole ownership story -- there is no second path to a Pet row in this
file, which is the point.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_pet
from app.models import ClientProfile, Pet, Role, User
from app.schemas.pet import PetCreate, PetOut, PetUpdate
from app.schemas.user import (
    CLIENT_PROFILE_FIELDS,
    VET_PROFILE_FIELDS,
    MyProfileUpdate,
    ProfileOut,
)
from app.services.pets import pet_has_history, pets_visible_to

router = APIRouter(prefix="/pets", tags=["pets"])
me_router = APIRouter(prefix="/me", tags=["profile"])

_NO_PROFILE = "No profile for this account"

# Not status.HTTP_422_UNPROCESSABLE_ENTITY: starlette renamed it to
# ..._UNPROCESSABLE_CONTENT and deprecated the old spelling, and the new one does
# not exist on the older starlette in api/Dockerfile's image. The number is the
# one thing both versions agree on.
_UNPROCESSABLE = 422


@router.get("", response_model=list[PetOut])
def list_pets(
    owner_id: int | None = Query(default=None, gt=0),
    q: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PetOut]:
    """A client's own pets; every pet in the clinic for a vet or an admin.

    `owner_id` and `q` are staff filters. A client passing owner_id does not get
    someone else's pets -- pets_visible_to ignores it for them.
    """
    stmt = pets_visible_to(current_user, owner_id=owner_id, q=q).limit(limit).offset(offset)
    return [PetOut.model_validate(pet) for pet in db.scalars(stmt)]


@router.post("", response_model=PetOut, status_code=status.HTTP_201_CREATED)
def create_pet(
    payload: PetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PetOut:
    """Register a pet.

    A client's pet is always their own: they may send their own owner_id or omit
    it, and naming anyone else is a 403 rather than a silent reassignment.

    Staff must say who the pet belongs to. There is no sensible default -- a vet
    has no client_profile of their own, so an omitted owner_id would have nowhere
    to point.
    """
    if current_user.role is Role.CLIENT:
        profile = current_user.client_profile
        if profile is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, _NO_PROFILE)
        if payload.owner_id is not None and payload.owner_id != profile.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your pet")
        owner_id = profile.id
    else:
        if payload.owner_id is None:
            raise HTTPException(
                _UNPROCESSABLE,
                "owner_id is required when staff create a pet",
            )
        if db.get(ClientProfile, payload.owner_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
        owner_id = payload.owner_id

    pet = Pet(
        owner_id=owner_id,
        **payload.model_dump(exclude={"owner_id"}),
    )
    db.add(pet)
    db.commit()
    db.refresh(pet)
    return PetOut.model_validate(pet)


@router.get("/{pet_id}", response_model=PetOut)
def read_pet(pet: Pet = Depends(get_owned_pet)) -> PetOut:
    """404 if there is no such pet, 403 if it is somebody else's."""
    return PetOut.model_validate(pet)


@router.patch("/{pet_id}", response_model=PetOut)
def update_pet(
    payload: PetUpdate,
    pet: Pet = Depends(get_owned_pet),
    db: Session = Depends(get_db),
) -> PetOut:
    """Partial update. An omitted field is left alone; an explicit null clears it.

    exclude_unset is what makes that distinction real: without it, every field the
    caller did not mention would be written back as None.
    """
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(pet, field, value)
    db.commit()
    db.refresh(pet)
    return PetOut.model_validate(pet)


@router.delete("/{pet_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pet(
    pet: Pet = Depends(get_owned_pet),
    db: Session = Depends(get_db),
) -> Response:
    """Remove a pet that has no clinical history.

    Deleting cascades into appointments, medical_records and vaccinations, so a
    pet that has been seen is refused with a 409 instead. Losing a vaccination
    record because an owner tidied up their account is not an acceptable outcome;
    if a pet really must go, its history has to be dealt with deliberately first.
    """
    if pet_has_history(db, pet.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Pet has appointments or medical history and cannot be deleted",
        )
    db.delete(pet)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# The caller's own profile
# ---------------------------------------------------------------------------


def _own_profile(user: User):
    """The caller's client_profiles or vet_profiles row, or a 404.

    An ADMIN has neither -- there is no admin profile table, which is exactly
    what /auth/staff builds (and what UserOut.from_user reports as a null
    full_name). 404 is the honest answer: we know who you are, there is simply
    no such resource. A 403 would claim the profile exists and is off-limits.
    """
    profile = user.client_profile or user.vet_profile
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NO_PROFILE)
    return profile


@me_router.get("/profile", response_model=ProfileOut)
def read_my_profile(current_user: User = Depends(get_current_user)) -> ProfileOut:
    """The caller's own profile row. Never anyone else's -- there is no id here."""
    _own_profile(current_user)
    return ProfileOut.from_user(current_user)


@me_router.patch("/profile", response_model=ProfileOut)
def update_my_profile(
    payload: MyProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    """Update the caller's own profile. Cannot touch the account itself.

    MyProfileUpdate carries both tables' fields, so a client sending `specialty`
    parses cleanly but has nowhere to store it. That is a 422, not a silent drop:
    the caller asked for something the server did not do.
    """
    profile = _own_profile(current_user)
    allowed = (
        CLIENT_PROFILE_FIELDS
        if current_user.role is Role.CLIENT
        else VET_PROFILE_FIELDS
    )

    changes = payload.model_dump(exclude_unset=True)
    rejected = sorted(set(changes) - allowed)
    if rejected:
        raise HTTPException(
            _UNPROCESSABLE,
            f"Not a field on this profile: {', '.join(rejected)}",
        )

    for field, value in changes.items():
        setattr(profile, field, value)
    try:
        db.commit()
    except IntegrityError:
        # vet_profiles.license_no is UNIQUE -- two vets cannot share one.
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Licence number already in use"
        ) from None
    db.refresh(profile)
    return ProfileOut.from_user(current_user)
