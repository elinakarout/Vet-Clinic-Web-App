"""Phase 3: a client manages their own pets and cannot touch anyone else's.

PROJECT_PLAN.md section 9 lists three pet tests. The one it calls "the important
one" -- client B gets 403 reading client A's pet -- is run here against all three
verbs, because a GET that is locked down while PATCH and DELETE are not is the
same bug with a longer fuse.

Every test goes over HTTP through api_client, so a route that forgets
Depends(get_owned_pet) fails here rather than in production.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Appointment, MedicalRecord, Pet, Vaccination

NEW_PET = {
    "name": "Bella",
    "species": "Dog",
    "breed": "Whippet",
    "sex": "FEMALE",
    "date_of_birth": "2022-03-14",
    "weight_kg": 12.5,
    "notes": "Hates the nail clippers.",
}


@pytest.fixture()
def client_a(login):
    return login("a@test.local", "a")


@pytest.fixture()
def client_b(login):
    return login("b@test.local", "b")


@pytest.fixture()
def vet(login):
    return login("vet@test.local", "vet")


# --------------------------------------------------------------------------
# PROJECT_PLAN.md section 9: the three
# --------------------------------------------------------------------------


def test_a_client_can_create_and_list_their_own_pets(
    api_client, seeded_db, client_a
):
    created = api_client.post("/pets", json=NEW_PET, headers=client_a)
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Bella"

    listed = api_client.get("/pets", headers=client_a).json()
    assert {pet["name"] for pet in listed} == {"Rex", "Bella"}
    # And nothing of client B's leaked in.
    assert all(pet["owner_id"] == seeded_db["client_a"].id for pet in listed)


def test_client_b_gets_403_reading_client_as_pet(api_client, seeded_db, client_b):
    """The single most common security bug in apps like this (PROJECT_PLAN.md)."""
    response = api_client.get(f"/pets/{seeded_db['pet_a'].id}", headers=client_b)
    assert response.status_code == 403
    assert response.json()["detail"] == "Not your pet"
    assert "name" not in response.json()


def test_a_vet_can_read_any_pet(api_client, seeded_db, vet):
    for key in ("pet_a", "pet_b"):
        response = api_client.get(f"/pets/{seeded_db[key].id}", headers=vet)
        assert response.status_code == 200, response.text


# --------------------------------------------------------------------------
# The same boundary, on the writing verbs
# --------------------------------------------------------------------------


def test_client_b_cannot_patch_client_as_pet(
    api_client, db_session, seeded_db, client_b
):
    response = api_client.patch(
        f"/pets/{seeded_db['pet_a'].id}", json={"name": "Stolen"}, headers=client_b
    )
    assert response.status_code == 403
    db_session.refresh(seeded_db["pet_a"])
    assert seeded_db["pet_a"].name == "Rex"


def test_client_b_cannot_delete_client_as_pet(
    api_client, db_session, seeded_db, client_b
):
    response = api_client.delete(
        f"/pets/{seeded_db['pet_a'].id}", headers=client_b
    )
    assert response.status_code == 403
    assert db_session.get(Pet, seeded_db["pet_a"].id) is not None


def test_a_client_sees_only_their_own_pets_in_the_list(
    api_client, seeded_db, client_b
):
    listed = api_client.get("/pets", headers=client_b).json()
    assert [pet["name"] for pet in listed] == ["Mittens"]


def test_a_client_cannot_widen_the_list_with_owner_id(
    api_client, seeded_db, client_b
):
    """owner_id is a staff filter. For a client it is ignored, never obeyed."""
    listed = api_client.get(
        f"/pets?owner_id={seeded_db['client_a'].id}", headers=client_b
    ).json()
    assert [pet["name"] for pet in listed] == ["Mittens"]


def test_an_admin_can_read_any_pet(api_client, login, seeded_db, admin_user):
    headers = login(admin_user.email, "admin1234")
    response = api_client.get(f"/pets/{seeded_db['pet_a'].id}", headers=headers)
    assert response.status_code == 200


def test_a_vet_lists_every_pet_in_the_clinic(api_client, seeded_db, vet):
    listed = api_client.get("/pets", headers=vet).json()
    assert {pet["name"] for pet in listed} == {"Rex", "Mittens"}


def test_staff_can_filter_the_list_by_owner_and_by_name(
    api_client, seeded_db, vet
):
    by_owner = api_client.get(
        f"/pets?owner_id={seeded_db['client_a'].id}", headers=vet
    ).json()
    assert [pet["name"] for pet in by_owner] == ["Rex"]

    by_name = api_client.get("/pets?q=mitt", headers=vet).json()
    assert [pet["name"] for pet in by_name] == ["Mittens"]

    by_species = api_client.get("/pets?q=CAT", headers=vet).json()
    assert [pet["name"] for pet in by_species] == ["Mittens"]


def test_the_list_paginates(api_client, seeded_db, vet):
    page = api_client.get("/pets?limit=1&offset=1", headers=vet).json()
    assert [pet["name"] for pet in page] == ["Rex"]  # ordered by name: Mittens, Rex


def test_a_pet_that_does_not_exist_is_404_not_403(api_client, seeded_db, client_a):
    """404 before the ownership check, so a client sees the same as a vet would."""
    assert api_client.get("/pets/999999", headers=client_a).status_code == 404


def test_the_pet_endpoints_need_a_token(api_client, seeded_db):
    pet_id = seeded_db["pet_a"].id
    assert api_client.get("/pets").status_code == 401
    assert api_client.post("/pets", json=NEW_PET).status_code == 401
    assert api_client.get(f"/pets/{pet_id}").status_code == 401
    assert api_client.patch(f"/pets/{pet_id}", json={"name": "x"}).status_code == 401
    assert api_client.delete(f"/pets/{pet_id}").status_code == 401


def test_a_deactivated_client_loses_access_to_their_own_pets(
    api_client, db_session, seeded_db, client_a
):
    """get_current_user re-reads the row, so the still-valid token stops working."""
    assert api_client.get("/pets", headers=client_a).status_code == 200

    seeded_db["client_a"].user.is_active = False
    db_session.commit()

    assert api_client.get("/pets", headers=client_a).status_code == 403


# --------------------------------------------------------------------------
# Creating
# --------------------------------------------------------------------------


def test_a_new_pet_is_owned_by_the_client_profile_not_the_user(
    api_client, db_session, seeded_db, client_a
):
    """The off-by-one-table bug, asserted head on.

    pets.owner_id is a client_profiles.id. In this fixture the user ids and the
    profile ids differ (the vet is user 1 but has no client profile), so writing
    user.id here would produce a pet owned by the wrong person -- or by nobody.
    """
    profile = seeded_db["client_a"]
    assert profile.id != profile.user_id  # otherwise this test proves nothing

    body = api_client.post("/pets", json=NEW_PET, headers=client_a).json()
    assert body["owner_id"] == profile.id

    assert body["owner_id"] != profile.user_id

    pet = db_session.get(Pet, body["id"])
    assert pet.owner is profile


def test_sex_defaults_to_unknown(api_client, seeded_db, client_a):
    body = api_client.post(
        "/pets", json={"name": "Nameless", "species": "Iguana"}, headers=client_a
    ).json()
    assert body["sex"] == "UNKNOWN"


def test_a_client_may_send_their_own_owner_id(api_client, seeded_db, client_a):
    response = api_client.post(
        "/pets",
        json={**NEW_PET, "owner_id": seeded_db["client_a"].id},
        headers=client_a,
    )
    assert response.status_code == 201


def test_a_client_cannot_create_a_pet_for_someone_else(
    api_client, seeded_db, client_a
):
    """Otherwise the ownership check on read would be trivially bypassable."""
    response = api_client.post(
        "/pets",
        json={**NEW_PET, "owner_id": seeded_db["client_b"].id},
        headers=client_a,
    )
    assert response.status_code == 403


def test_a_vet_must_say_who_the_pet_belongs_to(api_client, seeded_db, vet):
    """A vet has no client_profile, so there is no default owner to fall back on."""
    response = api_client.post("/pets", json=NEW_PET, headers=vet)
    assert response.status_code == 422


def test_a_vet_can_create_a_pet_for_a_named_client(
    api_client, seeded_db, vet
):
    response = api_client.post(
        "/pets",
        json={**NEW_PET, "owner_id": seeded_db["client_b"].id},
        headers=vet,
    )
    assert response.status_code == 201, response.text
    assert response.json()["owner_id"] == seeded_db["client_b"].id


def test_a_vet_naming_a_client_that_does_not_exist_gets_404(
    api_client, seeded_db, vet
):
    response = api_client.post(
        "/pets", json={**NEW_PET, "owner_id": 999999}, headers=vet
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Updating
# --------------------------------------------------------------------------


def test_a_patch_leaves_the_fields_it_does_not_mention_alone(
    api_client, seeded_db, client_a
):
    created = api_client.post("/pets", json=NEW_PET, headers=client_a).json()
    patched = api_client.patch(
        f"/pets/{created['id']}", json={"weight_kg": 13.1}, headers=client_a
    ).json()

    assert patched["weight_kg"] == 13.1
    assert patched["notes"] == NEW_PET["notes"]
    assert patched["breed"] == NEW_PET["breed"]


def test_an_explicit_null_clears_a_field(api_client, seeded_db, client_a):
    """exclude_unset is what makes "omitted" and "sent as null" different."""
    created = api_client.post("/pets", json=NEW_PET, headers=client_a).json()
    patched = api_client.patch(
        f"/pets/{created['id']}", json={"notes": None}, headers=client_a
    ).json()
    assert patched["notes"] is None


def test_an_empty_patch_body_is_rejected(api_client, seeded_db, client_a):
    response = api_client.patch(
        f"/pets/{seeded_db['pet_a'].id}", json={}, headers=client_a
    )
    assert response.status_code == 422


def test_a_patch_cannot_reassign_ownership(
    api_client, db_session, seeded_db, client_a
):
    """owner_id is absent from PetUpdate, so extra="forbid" makes this a 422."""
    response = api_client.patch(
        f"/pets/{seeded_db['pet_a'].id}",
        json={"owner_id": seeded_db["client_b"].id},
        headers=client_a,
    )
    assert response.status_code == 422
    db_session.refresh(seeded_db["pet_a"])
    assert seeded_db["pet_a"].owner_id == seeded_db["client_a"].id


def test_an_unknown_field_is_rejected(api_client, seeded_db, client_a):
    response = api_client.patch(
        f"/pets/{seeded_db['pet_a'].id}", json={"colour": "brindle"}, headers=client_a
    )
    assert response.status_code == 422


def test_a_vet_can_update_any_pet(api_client, seeded_db, vet):
    response = api_client.patch(
        f"/pets/{seeded_db['pet_a'].id}",
        json={"notes": "Seen for a limp."},
        headers=vet,
    )
    assert response.status_code == 200


# --------------------------------------------------------------------------
# Input rules -- rejected by the schema, before the database constraint
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"weight_kg": -1},          # ck_pets_weight_non_negative, as a 422
        {"date_of_birth": "3000-01-01"},
        {"name": "x" * 81},          # pets.name is String(80)
        {"species": "x" * 41},
        {"name": ""},
        {"sex": "YES"},
    ],
)
def test_bad_pet_input_is_422(api_client, seeded_db, client_a, bad):
    response = api_client.post("/pets", json={**NEW_PET, **bad}, headers=client_a)
    assert response.status_code == 422, response.text


def test_a_negative_weight_never_reaches_the_database(
    api_client, db_session, seeded_db, client_a
):
    """The check constraint is the backstop; the 422 is the actual contract."""
    api_client.post("/pets", json={**NEW_PET, "weight_kg": -5}, headers=client_a)
    assert db_session.query(Pet).filter(Pet.name == "Bella").count() == 0


# --------------------------------------------------------------------------
# Deleting
# --------------------------------------------------------------------------


def test_deleting_a_pet_with_no_history_works(api_client, seeded_db, client_a):
    created = api_client.post("/pets", json=NEW_PET, headers=client_a).json()
    assert api_client.delete(f"/pets/{created['id']}", headers=client_a).status_code == 204
    assert api_client.get(f"/pets/{created['id']}", headers=client_a).status_code == 404


def test_deleting_a_pet_with_appointments_is_409(
    api_client, db_session, seeded_db, client_a
):
    """The cascade would take the appointment with it, silently. It must not."""
    starts = datetime.now(timezone.utc) + timedelta(days=1)
    db_session.add(
        Appointment(
            pet_id=seeded_db["pet_a"].id,
            vet_id=seeded_db["vet"].id,
            starts_at=starts,
            ends_at=starts + timedelta(minutes=30),
        )
    )
    db_session.commit()

    response = api_client.delete(f"/pets/{seeded_db['pet_a'].id}", headers=client_a)
    assert response.status_code == 409
    assert db_session.get(Pet, seeded_db["pet_a"].id) is not None


def test_deleting_a_pet_with_a_medical_record_is_409(
    api_client, db_session, seeded_db, client_a
):
    db_session.add(
        MedicalRecord(
            pet_id=seeded_db["pet_a"].id,
            visit_date=datetime.now(timezone.utc),
            diagnosis="Sprained hock",
        )
    )
    db_session.commit()
    assert (
        api_client.delete(f"/pets/{seeded_db['pet_a'].id}", headers=client_a).status_code
        == 409
    )


def test_deleting_a_pet_with_a_vaccination_is_409(
    api_client, db_session, seeded_db, client_a
):
    db_session.add(
        Vaccination(
            pet_id=seeded_db["pet_a"].id,
            vaccine_name="Leptospirosis",
            given_at=date(2025, 6, 1),
        )
    )
    db_session.commit()
    assert (
        api_client.delete(f"/pets/{seeded_db['pet_a'].id}", headers=client_a).status_code
        == 409
    )


def test_a_vet_deleting_a_pet_with_history_is_also_409(
    api_client, db_session, seeded_db, vet
):
    """Staff bypass the *owner* check, not the history rule."""
    db_session.add(
        Vaccination(
            pet_id=seeded_db["pet_a"].id,
            vaccine_name="Rabies",
            given_at=date(2025, 6, 1),
        )
    )
    db_session.commit()
    assert (
        api_client.delete(f"/pets/{seeded_db['pet_a'].id}", headers=vet).status_code == 409
    )


# --------------------------------------------------------------------------
# /me/profile
# --------------------------------------------------------------------------


def test_a_client_reads_their_own_profile(api_client, seeded_db, client_a):
    body = api_client.get("/me/profile", headers=client_a).json()
    assert body["full_name"] == "Client A"
    assert body["role"] == "CLIENT"
    assert body["id"] == seeded_db["client_a"].id
    assert body["specialty"] is None
    assert "hashed_password" not in body


def test_a_vet_reads_their_own_profile(api_client, seeded_db, vet):
    body = api_client.get("/me/profile", headers=vet).json()
    assert body["role"] == "VET"
    assert body["specialty"] == "General"
    assert body["license_no"] == "VET-TEST-1"
    assert body["phone"] is None


def test_an_admin_has_no_profile(api_client, login, admin_user):
    """There is no admin profile table. 404 is the honest answer, not 403."""
    response = api_client.get("/me/profile", headers=login(admin_user.email, "admin1234"))
    assert response.status_code == 404
    assert response.json()["detail"] == "No profile for this account"


def test_the_profile_endpoints_need_a_token(api_client):
    assert api_client.get("/me/profile").status_code == 401
    assert api_client.patch("/me/profile", json={"phone": "1"}).status_code == 401


def test_a_client_can_update_their_own_profile(
    api_client, db_session, seeded_db, client_a
):
    body = api_client.patch(
        "/me/profile",
        json={"phone": "+44 117 000 0000", "address": "1 New Road"},
        headers=client_a,
    ).json()
    assert body["phone"] == "+44 117 000 0000"

    db_session.refresh(seeded_db["client_a"])
    assert seeded_db["client_a"].address == "1 New Road"
    assert seeded_db["client_a"].full_name == "Client A"  # untouched


def test_a_client_cannot_set_a_vet_field(api_client, seeded_db, client_a):
    """`specialty` parses fine but has nowhere to go on client_profiles."""
    response = api_client.patch(
        "/me/profile", json={"specialty": "Surgery"}, headers=client_a
    )
    assert response.status_code == 422
    assert "specialty" in response.json()["detail"]


def test_a_vet_cannot_set_a_client_field(api_client, seeded_db, vet):
    response = api_client.patch(
        "/me/profile", json={"address": "The clinic"}, headers=vet
    )
    assert response.status_code == 422


def test_a_profile_patch_cannot_change_the_account(api_client, seeded_db, client_a):
    """No email, no password, no role, no is_active -- extra="forbid" refuses them."""
    for smuggled in ({"role": "ADMIN"}, {"email": "new@x.test"}, {"is_active": False}):
        response = api_client.patch("/me/profile", json=smuggled, headers=client_a)
        assert response.status_code == 422, smuggled


def test_an_empty_profile_patch_is_rejected(api_client, seeded_db, client_a):
    assert api_client.patch("/me/profile", json={}, headers=client_a).status_code == 422


def test_a_duplicate_licence_number_is_409(
    api_client, db_session, login, seeded_db, admin_user
):
    """vet_profiles.license_no is UNIQUE -- the clash is a 409, never a 500."""
    api_client.post(
        "/auth/staff",
        json={
            "email": "second.vet@vetclinic.test",
            "password": "vetvet1234",
            "role": "VET",
            "full_name": "Dr. Second",
            "license_no": "VET-TEST-2",
        },
        headers=login(admin_user.email, "admin1234"),
    )
    headers = login("second.vet@vetclinic.test", "vetvet1234")

    response = api_client.patch(
        "/me/profile", json={"license_no": "VET-TEST-1"}, headers=headers
    )
    assert response.status_code == 409


def test_an_admin_cannot_patch_a_profile_they_do_not_have(
    api_client, login, admin_user
):
    response = api_client.patch(
        "/me/profile",
        json={"full_name": "The Boss"},
        headers=login(admin_user.email, "admin1234"),
    )
    assert response.status_code == 404
