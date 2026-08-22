"""Phase 1: the database layer keeps its promises without any HTTP involved.

These are the invariants later phases assume. If one of these breaks, the bug
shows up in Phase 3 or 4 as a mysterious 500 instead.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Appointment,
    AppointmentStatus,
    ClientProfile,
    KnowledgeChunk,
    KnowledgeDocument,
    MedicalRecord,
    Pet,
    Role,
    SourceType,
    User,
    VetAvailability,
)
from app.services.security import hash_password

SLOT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _appointment(pet_id: int, vet_id: int, status=AppointmentStatus.CONFIRMED, starts_at=SLOT):
    return Appointment(
        pet_id=pet_id,
        vet_id=vet_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        reason="Annual check-up",
        status=status,
    )


def test_all_tables_created(db_session):
    """create_all() sees every model -- the empty-migration trap in reverse."""
    tables = set(db_session.get_bind().dialect.get_table_names(db_session.connection()))
    assert {
        "users",
        "client_profiles",
        "vet_profiles",
        "pets",
        "vet_availability",
        "time_off",
        "appointments",
        "medical_records",
        "vaccinations",
        "knowledge_documents",
        "knowledge_chunks",
    } <= tables


def test_email_is_unique(db_session):
    db_session.add(User(email="dup@test.local", hashed_password=hash_password("x"), role=Role.CLIENT))
    db_session.commit()

    db_session.add(User(email="dup@test.local", hashed_password=hash_password("y"), role=Role.VET))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_password_is_never_stored_in_plaintext(db_session):
    user = User(email="hash@test.local", hashed_password=hash_password("hunter2"), role=Role.CLIENT)
    db_session.add(user)
    db_session.commit()

    assert user.hashed_password != "hunter2"
    assert user.hashed_password.startswith("$2")


def test_pet_owner_is_a_client_profile_not_a_user(seeded_db, db_session):
    """The off-by-one-table trap: pets.owner_id references client_profiles.id."""
    pet = seeded_db["pet_a"]
    profile = db_session.get(ClientProfile, pet.owner_id)

    assert profile is not None
    assert profile.full_name == "Client A"
    assert pet.owner.user.email == "a@test.local"


def test_pet_owner_id_pointing_at_a_user_id_is_rejected(seeded_db, db_session):
    """Foreign keys are actually enforced -- the SQLite PRAGMA is on."""
    orphan_id = max(db_session.scalars(select(ClientProfile.id)).all()) + 999
    db_session.add(Pet(owner_id=orphan_id, name="Ghost", species="Dog"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_a_pet_cascades_its_medical_records(seeded_db, db_session):
    pet = seeded_db["pet_a"]
    db_session.add(
        MedicalRecord(
            pet_id=pet.id,
            vet_id=seeded_db["vet"].id,
            visit_date=SLOT,
            diagnosis="Otitis externa",
            treatment="Ear drops, 7 days",
        )
    )
    db_session.commit()
    assert db_session.scalars(select(MedicalRecord)).all()

    db_session.delete(pet)
    db_session.commit()

    assert db_session.scalars(select(MedicalRecord)).all() == []


def test_deleting_a_client_user_cascades_profile_and_pets(seeded_db, db_session):
    user = db_session.scalar(select(User).where(User.email == "a@test.local"))
    db_session.delete(user)
    db_session.commit()

    assert db_session.scalars(select(ClientProfile).where(ClientProfile.full_name == "Client A")).all() == []
    assert db_session.scalars(select(Pet).where(Pet.name == "Rex")).all() == []
    # Client B is untouched.
    assert db_session.scalars(select(Pet).where(Pet.name == "Mittens")).all()


def test_double_booking_the_same_vet_slot_is_rejected(seeded_db, db_session):
    """Layer 1 of double-booking prevention, at the database itself."""
    db_session.add(_appointment(seeded_db["pet_a"].id, seeded_db["vet"].id))
    db_session.commit()

    db_session.add(_appointment(seeded_db["pet_b"].id, seeded_db["vet"].id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_cancelled_slot_can_be_rebooked(seeded_db, db_session):
    """Why the index is partial: cancelling frees the slot but keeps the history row."""
    first = _appointment(seeded_db["pet_a"].id, seeded_db["vet"].id)
    db_session.add(first)
    db_session.commit()

    first.status = AppointmentStatus.CANCELLED
    db_session.commit()

    db_session.add(_appointment(seeded_db["pet_b"].id, seeded_db["vet"].id))
    db_session.commit()  # must not raise

    appointments = db_session.scalars(select(Appointment)).all()
    assert len(appointments) == 2
    assert {a.status for a in appointments} == {
        AppointmentStatus.CANCELLED,
        AppointmentStatus.CONFIRMED,
    }


def test_two_vets_can_hold_the_same_time_slot(seeded_db, db_session):
    """Uniqueness is per vet, not global -- the clinic has more than one room."""
    second_vet_user = User(
        email="vet2@test.local", hashed_password=hash_password("v"), role=Role.VET
    )
    from app.models import VetProfile

    second_vet_user.vet_profile = VetProfile(full_name="Dr. Second", license_no="VET-TEST-2")
    db_session.add(second_vet_user)
    db_session.commit()

    db_session.add(_appointment(seeded_db["pet_a"].id, seeded_db["vet"].id))
    db_session.add(_appointment(seeded_db["pet_b"].id, second_vet_user.vet_profile.id))
    db_session.commit()  # must not raise

    assert len(db_session.scalars(select(Appointment)).all()) == 2


def test_appointment_cannot_end_before_it_starts(seeded_db, db_session):
    db_session.add(
        Appointment(
            pet_id=seeded_db["pet_a"].id,
            vet_id=seeded_db["vet"].id,
            starts_at=SLOT,
            ends_at=SLOT - timedelta(minutes=30),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize("weekday", [-1, 7])
def test_availability_weekday_must_be_0_to_6(seeded_db, db_session, weekday):
    from datetime import time

    db_session.add(
        VetAvailability(
            vet_id=seeded_db["vet"].id,
            weekday=weekday,
            start_time=time(9, 0),
            end_time=time(17, 0),
            slot_minutes=30,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_knowledge_chunks_are_unique_per_document_index(db_session):
    doc = KnowledgeDocument(title="Vaccination schedule", source_type=SourceType.CLINIC)
    db_session.add(doc)
    db_session.commit()

    db_session.add(KnowledgeChunk(document_id=doc.id, chunk_index=0, text="...", chroma_id=f"{doc.id}:0"))
    db_session.commit()

    db_session.add(KnowledgeChunk(document_id=doc.id, chunk_index=0, text="dup", chroma_id=f"{doc.id}:0-b"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_a_document_cascades_its_chunks(db_session):
    doc = KnowledgeDocument(title="Flea treatment", source_type=SourceType.EXTERNAL)
    doc.chunks = [
        KnowledgeChunk(chunk_index=i, text=f"chunk {i}", chroma_id=f"tmp:{i}") for i in range(3)
    ]
    db_session.add(doc)
    db_session.commit()

    db_session.delete(doc)
    db_session.commit()

    assert db_session.scalars(select(KnowledgeChunk)).all() == []
