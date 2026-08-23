"""Gives each test a fresh in-memory SQLite database. (Phase 1+)"""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

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
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        # ":memory:" is scoped to a *connection*, and the default for SQLite is
        # SingletonThreadPool -- one connection per thread. TestClient runs the
        # app in its own portal thread, which would therefore get a second,
        # empty database with no tables in it. StaticPool pins the engine to a
        # single shared connection so both threads see the same data.
        poolclass=StaticPool,
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


@pytest.fixture()
def api_client(db_session):
    """A TestClient wired to the *same* in-memory database as db_session.

    get_db hands back the test's own Session rather than opening a new one: two
    Sessions sharing one connection interleave their BEGIN/COMMIT, so a request
    committing would also commit whatever the test had pending. Deliberately
    does not close the session -- db_session owns its lifetime.

    Named api_client, not client: in this codebase a "client" is a pet owner.
    """

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def admin_user(db_session):
    """seeded_db has no admin, and /auth/staff needs one. Password: admin1234.

    ADMIN has no profile table, so this is a bare User row -- same as seed.py.
    """
    user = User(
        email="admin@test.local",
        hashed_password=hash_password("admin1234"),
        role=Role.ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def login(api_client):
    """Log in over HTTP and return an Authorization header dict."""

    def _login(email: str, password: str) -> dict[str, str]:
        response = api_client.post(
            # data=, not json=: the OAuth2 password flow is form-encoded, which
            # is exactly why python-multipart is a hard dependency.
            "/auth/login",
            data={"username": email, "password": password},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login
