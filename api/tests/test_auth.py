"""Phase 2: a token proves who you are, and nothing else gets you in.

PROJECT_PLAN.md section 9 lists five auth tests. Those five are the floor -- none
of them covers expiry, tampering, is_active, or the CLIENT-only rule, which is
where the bugs that matter actually live. If one of these breaks, it shows up in
Phase 3 as "client B can read client A's pet".
"""

from datetime import timedelta

import jwt
import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Role, User
from app.services.security import create_access_token, decode_token, verify_password

REGISTRATION = {
    "email": "new.client@example.test",
    "password": "hunter2222",
    "full_name": "New Client",
    "phone": "+44 7700 900000",
}


def _register(api_client, **overrides) -> "object":
    payload = {**REGISTRATION, **overrides}
    return api_client.post("/auth/register", json=payload)


def _user_by_email(db_session, email: str) -> User | None:
    return db_session.scalar(select(User).where(User.email == email))


# --------------------------------------------------------------------------
# PROJECT_PLAN.md section 9: the five
# --------------------------------------------------------------------------


def test_register_creates_a_user_with_a_hashed_password(api_client, db_session):
    """The password is bcrypt-hashed on the way in and absent on the way out."""
    response = _register(api_client)
    assert response.status_code == 201, response.text

    body = response.json()
    assert "hashed_password" not in body
    assert "password" not in body
    assert body["email"] == REGISTRATION["email"]
    assert body["role"] == "CLIENT"

    user = _user_by_email(db_session, REGISTRATION["email"])
    assert user.hashed_password != REGISTRATION["password"]
    assert user.hashed_password.startswith("$2")
    assert verify_password(REGISTRATION["password"], user.hashed_password)


def test_register_rejects_a_duplicate_email(api_client):
    """The second signup loses on the unique index, cleanly -- 409, not a 500."""
    assert _register(api_client).status_code == 201
    assert _register(api_client).status_code == 409


def test_login_with_the_right_password_returns_a_token(api_client, db_session):
    """And the token names the user who logged in."""
    _register(api_client)
    response = api_client.post(
        "/auth/login",
        data={"username": REGISTRATION["email"], "password": REGISTRATION["password"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"

    user = _user_by_email(db_session, REGISTRATION["email"])
    assert decode_token(body["access_token"])["sub"] == str(user.id)


def test_login_with_the_wrong_password_returns_401(api_client):
    """And says nothing about which half was wrong."""
    _register(api_client)
    response = api_client.post(
        "/auth/login",
        data={"username": REGISTRATION["email"], "password": "not-the-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_a_protected_endpoint_without_a_token_returns_401(api_client):
    """oauth2_scheme handles this one; the WWW-Authenticate header is the contract."""
    response = api_client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


# --------------------------------------------------------------------------
# Self-registration may only ever create CLIENT
# --------------------------------------------------------------------------


def test_register_cannot_choose_a_role(api_client, db_session):
    """The whole point of extra="forbid": smuggling a role is loud, not ignored."""
    response = _register(api_client, role="ADMIN")
    assert response.status_code == 422
    assert _user_by_email(db_session, REGISTRATION["email"]) is None


def test_register_creates_a_client_profile_and_no_vet_profile(api_client, db_session):
    """pets.owner_id points at client_profiles.id -- no profile, no pets ever."""
    _register(api_client)
    user = _user_by_email(db_session, REGISTRATION["email"])
    assert user.role is Role.CLIENT
    assert user.client_profile.full_name == REGISTRATION["full_name"]
    assert user.vet_profile is None


def test_me_returns_the_caller(api_client, login):
    """The section 5 manual check, automated."""
    _register(api_client)
    headers = login(REGISTRATION["email"], REGISTRATION["password"])
    body = api_client.get("/auth/me", headers=headers).json()
    assert body["email"] == REGISTRATION["email"]
    assert body["full_name"] == REGISTRATION["full_name"]
    assert "hashed_password" not in body


# --------------------------------------------------------------------------
# Staff creation is admin-only
# --------------------------------------------------------------------------

STAFF = {
    "email": "new.vet@vetclinic.test",
    "password": "vetvet1234",
    "role": "VET",
    "full_name": "Dr. New",
    "specialty": "Surgery",
    "license_no": "VET-NEW-1",
}


def test_an_admin_can_create_a_vet(api_client, login, admin_user, db_session):
    response = api_client.post(
        "/auth/staff", json=STAFF, headers=login(admin_user.email, "admin1234")
    )
    assert response.status_code == 201, response.text

    user = _user_by_email(db_session, STAFF["email"])
    assert user.role is Role.VET
    assert user.vet_profile.license_no == "VET-NEW-1"
    assert user.client_profile is None


def test_a_client_cannot_create_staff(api_client, login, seeded_db):
    """Otherwise self-registration being CLIENT-only would buy nothing."""
    response = api_client.post(
        "/auth/staff", json=STAFF, headers=login("a@test.local", "a")
    )
    assert response.status_code == 403


def test_a_vet_cannot_create_staff(api_client, login, seeded_db):
    """require_role checks membership of the listed roles, not merely "is staff"."""
    response = api_client.post(
        "/auth/staff", json=STAFF, headers=login("vet@test.local", "vet")
    )
    assert response.status_code == 403


def test_creating_staff_without_a_token_returns_401(api_client):
    assert api_client.post("/auth/staff", json=STAFF).status_code == 401


def test_the_staff_endpoint_refuses_the_client_role(api_client, login, admin_user):
    """CLIENT accounts go through /auth/register, which cannot be given a role."""
    response = api_client.post(
        "/auth/staff",
        json={**STAFF, "role": "CLIENT"},
        headers=login(admin_user.email, "admin1234"),
    )
    assert response.status_code == 422


def test_a_vet_created_by_an_admin_can_log_in(api_client, login, admin_user):
    """End to end: the account an admin creates is a real, usable login."""
    api_client.post(
        "/auth/staff", json=STAFF, headers=login(admin_user.email, "admin1234")
    )
    body = api_client.get(
        "/auth/me", headers=login(STAFF["email"], STAFF["password"])
    ).json()
    assert body["role"] == "VET"
    assert body["full_name"] == "Dr. New"


# --------------------------------------------------------------------------
# Token handling
# --------------------------------------------------------------------------


def test_an_expired_token_is_rejected(api_client, seeded_db):
    token = create_access_token(
        user_id=seeded_db["client_a"].user_id,
        role=Role.CLIENT,
        expires_delta=timedelta(minutes=-1),
    )
    response = api_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired"


def test_a_tampered_token_is_rejected(api_client, seeded_db):
    """Flip one character of the signature and the whole thing is worthless."""
    token = create_access_token(
        user_id=seeded_db["client_a"].user_id, role=Role.CLIENT
    )
    head, payload, signature = token.split(".")
    flipped = "A" if signature[0] != "A" else "B"
    tampered = f"{head}.{payload}.{flipped}{signature[1:]}"
    response = api_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tampered}"}
    )
    assert response.status_code == 401


def test_a_token_signed_with_another_secret_is_rejected(api_client, seeded_db):
    """The test that catches an accidental verify_signature=False."""
    forged = jwt.encode(
        {"sub": str(seeded_db["client_a"].user_id), "role": "ADMIN"},
        "a-different-secret-that-is-long-enough-to-not-warn",
        algorithm=settings.jwt_algorithm,
    )
    response = api_client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_a_token_naming_a_deleted_user_is_rejected(api_client):
    """Correctly signed, but there is nobody behind it."""
    token = create_access_token(user_id=999999, role=Role.CLIENT)
    response = api_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_a_token_with_a_non_numeric_subject_is_rejected(api_client):
    """`sub` is a string by RFC, but it still has to be an id we can look up."""
    token = jwt.encode(
        {"sub": "not-a-number"}, settings.secret_key, algorithm=settings.jwt_algorithm
    )
    response = api_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# --------------------------------------------------------------------------
# is_active
# --------------------------------------------------------------------------


def test_a_deactivated_user_cannot_log_in(api_client, db_session, seeded_db):
    user = seeded_db["client_a"].user
    user.is_active = False
    db_session.commit()

    response = api_client.post(
        "/auth/login", data={"username": "a@test.local", "password": "a"}
    )
    assert response.status_code == 403


def test_a_wrong_password_on_a_deactivated_account_still_says_401(
    api_client, db_session, seeded_db
):
    """is_active is checked *after* the password, so this is not an account oracle."""
    user = seeded_db["client_a"].user
    user.is_active = False
    db_session.commit()

    response = api_client.post(
        "/auth/login", data={"username": "a@test.local", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_deactivating_a_user_kills_their_existing_token(
    api_client, login, db_session, seeded_db
):
    """Why require_role re-reads the database instead of trusting the role claim.

    The token is still perfectly valid and unexpired -- it just no longer works.
    """
    headers = login("a@test.local", "a")
    assert api_client.get("/auth/me", headers=headers).status_code == 200

    seeded_db["client_a"].user.is_active = False
    db_session.commit()

    response = api_client.get("/auth/me", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Inactive user account"


# --------------------------------------------------------------------------
# Input rules
# --------------------------------------------------------------------------


def test_a_password_over_72_bytes_is_rejected(api_client):
    """bcrypt truncates at 72 bytes silently, so a 73-byte prefix would log you in."""
    assert _register(api_client, password="x" * 73).status_code == 422


def test_a_multibyte_password_is_measured_in_bytes_not_characters(api_client):
    """25 emoji are 25 characters but 100 bytes -- past the bcrypt limit."""
    assert _register(api_client, password="\U0001f436" * 25).status_code == 422


def test_a_short_password_is_rejected(api_client):
    assert _register(api_client, password="x" * 7).status_code == 422


@pytest.mark.parametrize("bad_email", ["not-an-email", "@example.test", "a@"])
def test_a_malformed_email_is_rejected(api_client, bad_email):
    assert _register(api_client, email=bad_email).status_code == 422


def test_email_is_case_insensitive(api_client):
    """users.email is a case-sensitive index, so the app normalises before it hits."""
    assert _register(api_client, email="Foo@Example.TEST").status_code == 201

    response = api_client.post(
        "/auth/login",
        data={"username": "foo@example.test", "password": REGISTRATION["password"]},
    )
    assert response.status_code == 200

    # And the same address in a third casing is still a duplicate.
    assert _register(api_client, email="FOO@EXAMPLE.TEST").status_code == 409


# ===========================================================================
# Login rate limiting (Phase 9)
#
# Phase 9's QA pass fired fifteen consecutive wrong passwords at a live server
# and got fifteen 401s, so an offline guessing loop was bounded only by bcrypt's
# cost factor. These tests pin the replacement.
# ===========================================================================


def _bad_login(api_client, email="client@example.test", password="wrongwrong"):
    return api_client.post(
        "/auth/login", data={"username": email, "password": password}
    )


def test_repeated_failed_logins_are_eventually_throttled(api_client, db_session, monkeypatch):
    """The point of the whole feature: guessing cannot run unbounded."""
    monkeypatch.setattr(settings, "login_rate_limit_per_minute", 3)
    _register(api_client, email="ratelimited@example.test", password="correct1234")

    codes = [
        _bad_login(api_client, "ratelimited@example.test").status_code for _ in range(5)
    ]
    assert codes[:3] == [401, 401, 401], codes
    assert codes[3:] == [429, 429], codes


def test_the_throttle_tells_the_caller_when_to_come_back(api_client, monkeypatch):
    """A 429 without Retry-After leaves a client guessing, so assert the header."""
    monkeypatch.setattr(settings, "login_rate_limit_per_minute", 1)
    _register(api_client, email="retry@example.test", password="correct1234")

    assert _bad_login(api_client, "retry@example.test").status_code == 401
    blocked = _bad_login(api_client, "retry@example.test")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    # It must not say whether the account exists.
    assert "password" not in blocked.json()["detail"].lower()


def test_a_correct_password_clears_the_penalty(api_client, monkeypatch):
    """Two typos then a success must not leave the next sign-in throttled."""
    monkeypatch.setattr(settings, "login_rate_limit_per_minute", 3)
    _register(api_client, email="typo@example.test", password="correct1234")

    assert _bad_login(api_client, "typo@example.test").status_code == 401
    assert _bad_login(api_client, "typo@example.test").status_code == 401
    good = api_client.post(
        "/auth/login",
        data={"username": "typo@example.test", "password": "correct1234"},
    )
    assert good.status_code == 200, good.text

    # The bucket was cleared, so the full budget is available again.
    assert _bad_login(api_client, "typo@example.test").status_code == 401
    assert _bad_login(api_client, "typo@example.test").status_code == 401
    assert _bad_login(api_client, "typo@example.test").status_code == 401
    assert _bad_login(api_client, "typo@example.test").status_code == 429


def test_throttling_one_account_does_not_lock_out_another(api_client, monkeypatch):
    """Keying on the e-mail alone would let anyone lock a known user out."""
    monkeypatch.setattr(settings, "login_rate_limit_per_minute", 2)
    _register(api_client, email="victim@example.test", password="correct1234")
    _register(api_client, email="bystander@example.test", password="correct1234")

    for _ in range(3):
        _bad_login(api_client, "victim@example.test")
    assert _bad_login(api_client, "victim@example.test").status_code == 429

    # The bystander shares the caller's address but not their bucket, and can
    # still sign in with the right password.
    good = api_client.post(
        "/auth/login",
        data={"username": "bystander@example.test", "password": "correct1234"},
    )
    assert good.status_code == 200, good.text


def test_an_unknown_address_is_throttled_too(api_client, monkeypatch):
    """Otherwise user enumeration by brute force stays free."""
    monkeypatch.setattr(settings, "login_rate_limit_per_minute", 2)
    codes = [
        _bad_login(api_client, "nobody@example.test").status_code for _ in range(4)
    ]
    assert codes == [401, 401, 429, 429], codes


def test_the_limit_can_be_switched_off(api_client, monkeypatch):
    """0 disables it -- how a local REPL or a load test turns throttling off."""
    monkeypatch.setattr(settings, "login_rate_limit_per_minute", 0)
    codes = [
        _bad_login(api_client, "nobody@example.test").status_code for _ in range(12)
    ]
    assert set(codes) == {401}, codes
