"""Pet queries that are not HTTP concerns. (Phase 3)

Nothing here raises HTTPException or knows what a status code is (CLAUDE.md's
layering rule). The ownership *check* lives in deps.get_owned_pet because it
must raise 403/404; the ownership *scope* lives here because it is a query.
"""

from sqlalchemy import Select, exists, or_, select
from sqlalchemy.orm import Session

from app.models import Appointment, MedicalRecord, Pet, Role, User, Vaccination


def pets_visible_to(
    user: User,
    *,
    owner_id: int | None = None,
    q: str | None = None,
) -> Select:
    """The `SELECT` a given user is allowed to run over pets.

    A CLIENT is pinned to their own client_profile.id and the `owner_id`
    argument is ignored outright -- narrowing a scope is a filter, widening one
    would be a privilege escalation dressed as a query parameter. VET and ADMIN
    see every patient, which is what makes `owner_id` and `q` useful at all:
    finding the right Bella before booking her in.

    Returns the statement rather than the rows so the router can apply
    limit/offset without this function growing pagination concerns.
    """
    stmt = select(Pet)

    if user.role is Role.CLIENT:
        # A client with no profile row owns no pets; -1 matches nothing rather
        # than raising, so the endpoint answers with an empty list.
        profile = user.client_profile
        stmt = stmt.where(Pet.owner_id == (profile.id if profile is not None else -1))
    elif owner_id is not None:
        stmt = stmt.where(Pet.owner_id == owner_id)

    if q:
        # ilike, so "bella" finds "Bella". On SQLite LIKE is already
        # case-insensitive for ASCII; on PostgreSQL it would not be.
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Pet.name.ilike(pattern), Pet.species.ilike(pattern)))

    return stmt.order_by(Pet.name, Pet.id)


def pet_has_history(db: Session, pet_id: int) -> bool:
    """True if deleting this pet would destroy clinical history.

    models.Pet cascades delete-orphan into appointments, medical_records and
    vaccinations, so a DELETE is silent and total. A clinic does not get to lose
    a vaccination record because an owner tidied up their account, so the router
    turns this into a 409 instead.
    """
    return bool(
        db.scalar(
            select(
                exists().where(Appointment.pet_id == pet_id)
                | exists().where(MedicalRecord.pet_id == pet_id)
                | exists().where(Vaccination.pet_id == pet_id)
            )
        )
    )
