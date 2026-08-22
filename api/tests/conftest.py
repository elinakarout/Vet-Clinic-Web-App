"""Gives each test a fresh in-memory SQLite database. (Phase 1+)"""

from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base

# Importing the package registers all eleven tables on Base.metadata. Without
# it create_all() below silently creates nothing.
from app import models  # noqa: F401  (must precede create_all)
from app.models import (
    ClientProfile,
    Pet,
    Role,
    Sex,
    User,
    VetAvailability,
    VetProfile,
)
from app.services.security import hash_password


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded_db(db_session):
    """A miniature version of scripts/seed.py: one vet, two clients, two pets.

    Deliberately gives each client exactly one pet, so ownership tests ("client B
    gets 403 on client A's pet") have the rows they need.
    """
    vet_user = User(
        email="vet@test.local", hashed_password=hash_password("vet"), role=Role.VET
    )
    vet_user.vet_profile = VetProfile(
        full_name="Dr. Test",
        specialty="General",
        license_no="VET-TEST-1",
        availability=[
            VetAvailability(
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(17, 0),
                slot_minutes=30,
            )
            for weekday in range(0, 5)
        ],
    )

    client_a = User(
        email="a@test.local", hashed_password=hash_password("a"), role=Role.CLIENT
    )
    client_a.client_profile = ClientProfile(
        full_name="Client A",
        pets=[Pet(name="Rex", species="Dog", sex=Sex.MALE, date_of_birth=date(2020, 1, 1))],
    )

    client_b = User(
        email="b@test.local", hashed_password=hash_password("b"), role=Role.CLIENT
    )
    client_b.client_profile = ClientProfile(
        full_name="Client B",
        pets=[Pet(name="Mittens", species="Cat", sex=Sex.FEMALE)],
    )

    db_session.add_all([vet_user, client_a, client_b])
    db_session.commit()

    return {
        "vet_user": vet_user,
        "vet": vet_user.vet_profile,
        "client_a": client_a.client_profile,
        "client_b": client_b.client_profile,
        "pet_a": client_a.client_profile.pets[0],
        "pet_b": client_b.client_profile.pets[0],
    }
