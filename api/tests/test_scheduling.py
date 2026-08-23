"""Slot generation and double-booking tests, incl. booking twice returns 409. (Phase 4)

Everything runs over HTTP through `api_client`, so a route that forgets
Depends(get_owned_appointment) fails here rather than in production.

PROJECT_PLAN.md section 9 lists five tests for this phase and they are the floor:
slots respect working hours, slots exclude time-off, slots exclude booked times,
**booking the same slot twice returns 409**, and a client can only cancel their
own appointment. The rest of this file covers what Phase 4 can actually get
wrong -- timezone handling and the UTC-normalisation hole that would otherwise
let two bookings for the same instant both succeed.

tests/test_models.py already proves the uq_vet_active_slot index fires at ORM
level. This file does not re-test the index; it tests the HTTP behaviour on top
of it.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models import Appointment, AppointmentStatus, Role, TimeOff, User, VetAvailability, VetProfile
from app.services.security import hash_password
from app.services.timeutils import CLINIC_TZ, local_to_utc, now_utc, utc_to_clinic

BEIRUT = ZoneInfo("Asia/Beirut")


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------


def _clinic_today() -> date:
    return utc_to_clinic(now_utc()).date()


def _business_day(offset: int = 7) -> date:
    """A clinic-local weekday comfortably in the future.

    seeded_db's vet works Monday to Friday, and generate_slots drops anything in
    the past, so a test that picks "today" is a test that fails after 17:00.
    """
    day = _clinic_today() + timedelta(days=offset)
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


def _slots(api_client, headers, vet_id, day, day_to=None):
    response = api_client.get(
        "/appointments/slots",
        params={
            "vet_id": vet_id,
            "date_from": day.isoformat(),
            "date_to": (day_to or day).isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _book(api_client, headers, *, pet_id, vet_id, starts_at, reason="Checkup"):
    return api_client.post(
        "/appointments",
        json={
            "pet_id": pet_id,
            "vet_id": vet_id,
            "starts_at": starts_at,
            "reason": reason,
        },
        headers=headers,
    )


def _insert_appointment(db, *, pet, vet, starts_at, minutes=30, status=AppointmentStatus.CONFIRMED):
    """Put an appointment straight into the database.

    Used only where the *time* is the point of the test -- a cancellation inside
    the two-hour cutoff, or one that has already started. Those cannot be created
    through POST /appointments, because booking refuses a slot in the past and
    the availability grid does not have an opening an hour from now on demand.
    """
    appointment = Appointment(
        pet_id=pet.id,
        vet_id=vet.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=minutes),
        status=status,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


@pytest.fixture()
def client_a_headers(seeded_db, login):
    return login("a@test.local", "a")


@pytest.fixture()
def client_b_headers(seeded_db, login):
    return login("b@test.local", "b")


@pytest.fixture()
def vet_headers(seeded_db, login):
    return login("vet@test.local", "vet")


@pytest.fixture()
def admin_headers(admin_user, login):
    return login("admin@test.local", "admin1234")


@pytest.fixture()
def other_vet(db_session):
    """A second vet, for the "may not edit a colleague's calendar" tests."""
    user = User(
        email="vet2@test.local", hashed_password=hash_password("vet2"), role=Role.VET
    )
    user.vet_profile = VetProfile(full_name="Dr. Other", license_no="VET-TEST-2")
    db_session.add(user)
    db_session.commit()
    return user.vet_profile


# ---------------------------------------------------------------------------
# Slot generation
# ---------------------------------------------------------------------------


def test_slots_respect_the_vets_working_hours(api_client, seeded_db, client_a_headers):
    """9am-5pm in 30-minute steps is 16 slots, first at 09:00 clinic time."""
    day = _business_day()
    slots = _slots(api_client, client_a_headers, seeded_db["vet"].id, day)

    assert len(slots) == 16
    locals_ = [utc_to_clinic(datetime.fromisoformat(s["starts_at"])) for s in slots]
    assert locals_[0].time() == time(9, 0)
    assert locals_[-1].time() == time(16, 30)
    assert all(local.date() == day for local in locals_)


def test_a_weekend_has_no_slots(api_client, seeded_db, client_a_headers):
    day = _clinic_today() + timedelta(days=1)
    while day.weekday() != 5:  # Saturday
        day += timedelta(days=1)
    assert _slots(api_client, client_a_headers, seeded_db["vet"].id, day) == []


def test_a_past_date_yields_no_slots(api_client, seeded_db, client_a_headers):
    day = _clinic_today() - timedelta(days=3)
    assert _slots(api_client, client_a_headers, seeded_db["vet"].id, day) == []


def test_every_slot_returned_is_in_the_future(api_client, seeded_db, client_a_headers):
    """Today's list must never offer a time that has already gone."""
    slots = _slots(api_client, client_a_headers, seeded_db["vet"].id, _clinic_today())
    now = now_utc()
    assert all(datetime.fromisoformat(s["starts_at"]) >= now for s in slots)


def test_no_slot_ends_after_closing_time(api_client, db_session, seeded_db, admin_headers):
    """A 50-minute slot does not fit eight times into an eight-hour day.

    The last opening must be 15:40-16:30, not 16:30-17:20. Getting this wrong is
    the classic off-by-one in a slot walker, and it books patients past closing.
    """
    vet_id = seeded_db["vet"].id
    day = _business_day()
    response = api_client.put(
        f"/vets/{vet_id}/availability",
        json=[
            {
                "weekday": day.weekday(),
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "slot_minutes": 50,
            }
        ],
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text

    slots = _slots(api_client, admin_headers, vet_id, day)
    assert len(slots) == 9
    last_end = utc_to_clinic(datetime.fromisoformat(slots[-1]["ends_at"]))
    assert last_end.time() == time(16, 30)
    assert all(
        utc_to_clinic(datetime.fromisoformat(s["ends_at"])).time() <= time(17, 0)
        for s in slots
    )


def test_slots_exclude_a_time_off_block(api_client, db_session, seeded_db, client_a_headers):
    """PROJECT_PLAN section 9: slots exclude time-off blocks."""
    vet_id = seeded_db["vet"].id
    day = _business_day()
    before = _slots(api_client, client_a_headers, vet_id, day)

    db_session.add(
        TimeOff(
            vet_id=vet_id,
            starts_at=local_to_utc(day, time(9, 0)),
            ends_at=local_to_utc(day, time(12, 0)),
            reason="Surgery list",
        )
    )
    db_session.commit()

    after = _slots(api_client, client_a_headers, vet_id, day)
    assert len(after) == len(before) - 6  # 09:00-12:00 is six 30-minute slots
    assert all(
        utc_to_clinic(datetime.fromisoformat(s["starts_at"])).time() >= time(12, 0)
        for s in after
    )


def test_a_time_off_block_that_only_clips_a_slot_still_removes_it(
    api_client, db_session, seeded_db, client_a_headers
):
    """Overlap, not equality. A block from 09:15 to 09:20 kills the 09:00 slot."""
    vet_id = seeded_db["vet"].id
    day = _business_day()
    db_session.add(
        TimeOff(
            vet_id=vet_id,
            starts_at=local_to_utc(day, time(9, 15)),
            ends_at=local_to_utc(day, time(9, 20)),
        )
    )
    db_session.commit()

    starts = [
        utc_to_clinic(datetime.fromisoformat(s["starts_at"])).time()
        for s in _slots(api_client, client_a_headers, vet_id, day)
    ]
    assert time(9, 0) not in starts
    assert time(9, 30) in starts


def test_slots_exclude_an_already_booked_time(api_client, seeded_db, client_a_headers):
    """PROJECT_PLAN section 9: slots exclude already-booked times."""
    vet_id = seeded_db["vet"].id
    day = _business_day()
    before = _slots(api_client, client_a_headers, vet_id, day)

    booked = before[0]["starts_at"]
    assert _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=vet_id,
        starts_at=booked,
    ).status_code == 201

    after = _slots(api_client, client_a_headers, vet_id, day)
    assert len(after) == len(before) - 1
    assert booked not in [s["starts_at"] for s in after]


def test_a_cancelled_appointment_puts_its_slot_back(api_client, seeded_db, client_a_headers):
    """The whole reason uq_vet_active_slot is a *partial* index, end to end."""
    vet_id = seeded_db["vet"].id
    day = _business_day()
    original = _slots(api_client, client_a_headers, vet_id, day)
    target = original[0]["starts_at"]

    created = _book(
        api_client, client_a_headers, pet_id=seeded_db["pet_a"].id, vet_id=vet_id, starts_at=target
    )
    assert created.status_code == 201, created.text
    assert target not in [s["starts_at"] for s in _slots(api_client, client_a_headers, vet_id, day)]

    cancelled = api_client.post(
        f"/appointments/{created.json()['id']}/cancel", headers=client_a_headers
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"

    assert [s["starts_at"] for s in _slots(api_client, client_a_headers, vet_id, day)] == [
        s["starts_at"] for s in original
    ]


def test_a_vet_with_no_availability_has_no_slots(api_client, seeded_db, admin_headers):
    vet_id = seeded_db["vet"].id
    assert api_client.put(
        f"/vets/{vet_id}/availability", json=[], headers=admin_headers
    ).status_code == 200
    assert _slots(api_client, admin_headers, vet_id, _business_day()) == []


def test_slots_for_an_unknown_vet_are_404(api_client, seeded_db, client_a_headers):
    day = _business_day()
    response = api_client.get(
        "/appointments/slots",
        params={"vet_id": 9999, "date_from": day.isoformat(), "date_to": day.isoformat()},
        headers=client_a_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Vet not found"


def test_slots_reject_a_backwards_date_range(api_client, seeded_db, client_a_headers):
    day = _business_day()
    response = api_client.get(
        "/appointments/slots",
        params={
            "vet_id": seeded_db["vet"].id,
            "date_from": day.isoformat(),
            "date_to": (day - timedelta(days=1)).isoformat(),
        },
        headers=client_a_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "date_to cannot be before date_from"


def test_slots_reject_an_oversized_date_range(api_client, seeded_db, client_a_headers):
    day = _business_day()
    response = api_client.get(
        "/appointments/slots",
        params={
            "vet_id": seeded_db["vet"].id,
            "date_from": day.isoformat(),
            "date_to": (day + timedelta(days=400)).isoformat(),
        },
        headers=client_a_headers,
    )
    assert response.status_code == 422
    assert "31 days" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Time zones
#
# The clinic is Asia/Beirut: UTC+2 in winter, UTC+3 in summer. If someone
# "simplifies" the timezone handling away and treats the Time columns as UTC,
# these are the tests that go red.
# ---------------------------------------------------------------------------


def test_nine_am_clinic_time_is_seven_utc_in_winter_and_six_in_summer():
    """A pure-function check on fixed dates, so it does not drift with the clock."""
    assert local_to_utc(date(2026, 1, 15), time(9, 0)) == datetime(
        2026, 1, 15, 7, 0, tzinfo=timezone.utc
    )
    assert local_to_utc(date(2026, 7, 15), time(9, 0)) == datetime(
        2026, 7, 15, 6, 0, tzinfo=timezone.utc
    )


def test_a_local_time_the_dst_change_skips_does_not_exist():
    """Asia/Beirut jumps 00:00 -> 01:00 on 2026-03-29. 00:30 never happens."""
    assert local_to_utc(date(2026, 3, 29), time(0, 30)) is None
    assert local_to_utc(date(2026, 3, 29), time(1, 30)) is not None


def test_slot_start_times_are_clinic_local_not_utc(api_client, seeded_db, client_a_headers):
    """The vet opens at 09:00 in Beirut, so the first slot is 06:00Z or 07:00Z."""
    day = _business_day()
    first = datetime.fromisoformat(
        _slots(api_client, client_a_headers, seeded_db["vet"].id, day)[0]["starts_at"]
    )
    assert utc_to_clinic(first).time() == time(9, 0)
    assert first.hour in (6, 7)  # never 9 -- that would be 09:00 read as UTC


def test_appointment_times_come_back_as_explicit_utc(api_client, seeded_db, client_a_headers):
    """Aware, with an offset. A naive string would let the frontend guess local."""
    day = _business_day()
    target = _slots(api_client, client_a_headers, seeded_db["vet"].id, day)[0]["starts_at"]
    body = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=target,
    ).json()

    for field in ("starts_at", "ends_at"):
        parsed = datetime.fromisoformat(body[field])
        assert parsed.tzinfo is not None, body[field]
        assert parsed.utcoffset() == timedelta(0)


def test_a_naive_starts_at_is_rejected(api_client, seeded_db, client_a_headers):
    """Ambiguous by two or three hours depending on the season. Ask, do not guess."""
    day = _business_day()
    naive = utc_to_clinic(
        datetime.fromisoformat(
            _slots(api_client, client_a_headers, seeded_db["vet"].id, day)[0]["starts_at"]
        )
    ).replace(tzinfo=None)

    response = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=naive.isoformat(),
    )
    assert response.status_code == 422
    assert "offset" in response.text


def test_the_same_instant_in_another_offset_is_the_same_slot(
    api_client, db_session, seeded_db, client_a_headers, client_b_headers
):
    """09:00Z and 12:00+03:00 are one instant and therefore one slot.

    The companion to test_booking_in_a_non_utc_offset_is_stored_as_utc below,
    which is the one with teeth: this direction is caught by the slot check even
    without UTC normalisation, because Python compares aware datetimes by
    instant. Kept because it is the behaviour a caller actually depends on.
    """
    vet_id = seeded_db["vet"].id
    day = _business_day()
    utc_form = _slots(api_client, client_a_headers, vet_id, day)[0]["starts_at"]
    beirut_form = datetime.fromisoformat(utc_form).astimezone(BEIRUT).isoformat()
    assert beirut_form != utc_form
    assert datetime.fromisoformat(beirut_form) == datetime.fromisoformat(utc_form)

    first = _book(
        api_client, client_a_headers, pet_id=seeded_db["pet_a"].id, vet_id=vet_id, starts_at=utc_form
    )
    assert first.status_code == 201, first.text

    second = _book(
        api_client,
        client_b_headers,
        pet_id=seeded_db["pet_b"].id,
        vet_id=vet_id,
        starts_at=beirut_form,
    )
    assert second.status_code == 409, second.text

    held = db_session.scalars(
        select(Appointment).where(Appointment.vet_id == vet_id)
    ).all()
    assert len(held) == 1



def test_booking_in_a_non_utc_offset_is_stored_as_utc(
    api_client, db_session, seeded_db, client_a_headers
):
    """The measured hole this phase exists to close.

    SQLite discards the offset on write: an aware 09:00+03:00 stores the *string*
    "09:00", three hours from the instant it names. Everything downstream then
    reads it back as 09:00 UTC -- so the booked slot goes on being offered as
    free, and uq_vet_active_slot guards a time nobody asked for.

    Verified by mutation while writing this phase. Dropping the to_utc() call in
    book_appointment makes this assertion read
    `datetime(2026, 8, 31, 9, 0) == datetime(2026, 8, 31, 6, 0)`.
    """
    vet_id = seeded_db["vet"].id
    day = _business_day()
    utc_form = _slots(api_client, client_a_headers, vet_id, day)[0]["starts_at"]
    beirut_form = datetime.fromisoformat(utc_form).astimezone(BEIRUT).isoformat()
    assert beirut_form != utc_form  # same instant, different spelling

    created = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=vet_id,
        starts_at=beirut_form,
    )
    assert created.status_code == 201, created.text

    stored = db_session.scalars(select(Appointment.starts_at)).one()
    assert stored.replace(tzinfo=None) == datetime.fromisoformat(utc_form).replace(tzinfo=None)

    # ...and the consequence that makes it matter: the slot is really gone.
    assert utc_form not in [
        s["starts_at"] for s in _slots(api_client, client_a_headers, vet_id, day)
    ]


def test_a_stale_slot_check_still_cannot_double_book(
    api_client, db_session, seeded_db, monkeypatch, client_a_headers, client_b_headers
):
    """Layer 2 on its own, with layer 1's check deliberately lying.

    "Check if free, then insert" is a race: between the two lines another request
    can slip in. Every other test here is served by the check, so this one stubs
    generate_slots to report a slot that is *already taken* -- exactly what a
    stale read looks like -- and asserts the database refuses it and the router
    turns that into a 409 rather than a 500.
    """
    from app.services import scheduling

    vet_id = seeded_db["vet"].id
    day = _business_day()
    target = _slots(api_client, client_a_headers, vet_id, day)[0]["starts_at"]
    assert _book(
        api_client, client_a_headers, pet_id=seeded_db["pet_a"].id, vet_id=vet_id, starts_at=target
    ).status_code == 201

    taken = datetime.fromisoformat(target)
    monkeypatch.setattr(
        scheduling,
        "generate_slots",
        lambda *a, **k: [
            scheduling.Slot(
                starts_at=taken,
                ends_at=taken + timedelta(minutes=30),
                vet_id=vet_id,
                slot_minutes=30,
            )
        ],
    )

    second = _book(
        api_client, client_b_headers, pet_id=seeded_db["pet_b"].id, vet_id=vet_id, starts_at=target
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"] == "That time was just booked. Please pick another."
    assert db_session.query(Appointment).count() == 1


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


def test_a_client_books_a_slot_for_their_own_pet(api_client, seeded_db, client_a_headers):
    day = _business_day()
    target = _slots(api_client, client_a_headers, seeded_db["vet"].id, day)[0]["starts_at"]

    response = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=target,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "CONFIRMED"
    assert body["pet_id"] == seeded_db["pet_a"].id
    assert body["reason"] == "Checkup"
    assert datetime.fromisoformat(body["ends_at"]) - datetime.fromisoformat(
        body["starts_at"]
    ) == timedelta(minutes=30)


def test_booking_records_who_made_it(api_client, db_session, seeded_db, client_a_headers, vet_headers):
    """created_by distinguishes a self-service booking from a receptionist's."""
    day = _business_day()
    slots = _slots(api_client, client_a_headers, seeded_db["vet"].id, day)

    own = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=slots[0]["starts_at"],
    ).json()
    by_staff = _book(
        api_client,
        vet_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=slots[1]["starts_at"],
    ).json()

    client_user_id = seeded_db["client_a"].user_id
    assert own["created_by"] == client_user_id
    assert by_staff["created_by"] != client_user_id


def test_a_client_cannot_book_for_another_clients_pet(api_client, seeded_db, client_a_headers):
    """The get_owned_pet boundary, reached through the request body."""
    day = _business_day()
    target = _slots(api_client, client_a_headers, seeded_db["vet"].id, day)[0]["starts_at"]

    response = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_b"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=target,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not your pet"


def test_staff_may_book_for_any_pet(api_client, seeded_db, vet_headers, client_a_headers):
    day = _business_day()
    target = _slots(api_client, client_a_headers, seeded_db["vet"].id, day)[0]["starts_at"]

    response = _book(
        api_client,
        vet_headers,
        pet_id=seeded_db["pet_b"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=target,
    )
    assert response.status_code == 201, response.text


def test_booking_a_time_off_the_slot_grid_is_refused(api_client, db_session, seeded_db, client_a_headers):
    """09:07 is inside working hours but is not an opening."""
    day = _business_day()
    misaligned = local_to_utc(day, time(9, 7))

    response = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=misaligned.isoformat(),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "That time is not available"
    assert db_session.query(Appointment).count() == 0


def test_booking_outside_working_hours_is_refused(api_client, db_session, seeded_db, client_a_headers):
    day = _business_day()
    response = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=local_to_utc(day, time(20, 0)).isoformat(),
    )
    assert response.status_code == 409
    assert db_session.query(Appointment).count() == 0


def test_booking_in_the_past_is_refused(api_client, db_session, seeded_db, client_a_headers):
    past = _clinic_today() - timedelta(days=7)
    while past.weekday() > 4:
        past -= timedelta(days=1)

    response = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=local_to_utc(past, time(9, 0)).isoformat(),
    )
    assert response.status_code == 409
    assert db_session.query(Appointment).count() == 0


def test_booking_inside_a_time_off_block_is_refused(api_client, db_session, seeded_db, client_a_headers):
    vet_id = seeded_db["vet"].id
    day = _business_day()
    target = local_to_utc(day, time(9, 0))
    db_session.add(
        TimeOff(vet_id=vet_id, starts_at=target, ends_at=local_to_utc(day, time(12, 0)))
    )
    db_session.commit()

    response = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=vet_id,
        starts_at=target.isoformat(),
    )
    assert response.status_code == 409
    assert db_session.query(Appointment).count() == 0


def test_booking_too_far_ahead_is_refused(api_client, seeded_db, client_a_headers):
    far = _clinic_today() + timedelta(days=400)
    while far.weekday() > 4:
        far += timedelta(days=1)

    response = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=local_to_utc(far, time(9, 0)).isoformat(),
    )
    assert response.status_code == 422
    assert "365 days" in response.json()["detail"]


def test_booking_with_an_unknown_vet_is_404(api_client, seeded_db, client_a_headers):
    day = _business_day()
    response = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=9999,
        starts_at=local_to_utc(day, time(9, 0)).isoformat(),
    )
    assert response.status_code == 404


def test_booking_with_a_deactivated_vet_is_404(api_client, db_session, seeded_db, client_a_headers):
    """A vet keeps their row when they leave; they stop being bookable."""
    day = _business_day()
    target = local_to_utc(day, time(9, 0)).isoformat()
    seeded_db["vet_user"].is_active = False
    db_session.commit()

    response = _book(
        api_client,
        client_a_headers,
        pet_id=seeded_db["pet_a"].id,
        vet_id=seeded_db["vet"].id,
        starts_at=target,
    )
    assert response.status_code == 404


def test_a_pet_cannot_be_booked_with_two_vets_at_once(
    api_client, db_session, seeded_db, other_vet, client_a_headers, admin_headers
):
    """uq_vet_active_slot is keyed on the vet, so nothing in the schema stops this."""
    day = _business_day()
    assert api_client.put(
        f"/vets/{other_vet.id}/availability",
        json=[
            {
                "weekday": day.weekday(),
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "slot_minutes": 30,
            }
        ],
        headers=admin_headers,
    ).status_code == 200

    target = local_to_utc(day, time(9, 0)).isoformat()
    first = _book(
        api_client, client_a_headers, pet_id=seeded_db["pet_a"].id, vet_id=seeded_db["vet"].id, starts_at=target
    )
    assert first.status_code == 201, first.text

    second = _book(
        api_client, client_a_headers, pet_id=seeded_db["pet_a"].id, vet_id=other_vet.id, starts_at=target
    )
    assert second.status_code == 409
    assert "already has an appointment" in second.json()["detail"]


def test_an_unknown_field_in_the_booking_body_is_422(api_client, seeded_db, client_a_headers):
    """Notably including "status": booking always produces CONFIRMED."""
    day = _business_day()
    response = api_client.post(
        "/appointments",
        json={
            "pet_id": seeded_db["pet_a"].id,
            "vet_id": seeded_db["vet"].id,
            "starts_at": local_to_utc(day, time(9, 0)).isoformat(),
            "status": "COMPLETED",
        },
        headers=client_a_headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Double booking -- PROJECT_PLAN section 9 calls this the important one
# ---------------------------------------------------------------------------


def test_booking_the_same_slot_twice_returns_409(
    api_client, db_session, seeded_db, client_a_headers, client_b_headers
):
    """Two clients, one slot. The second gets a clean 409, never a 500."""
    vet_id = seeded_db["vet"].id
    day = _business_day()
    target = _slots(api_client, client_a_headers, vet_id, day)[0]["starts_at"]

    first = _book(
        api_client, client_a_headers, pet_id=seeded_db["pet_a"].id, vet_id=vet_id, starts_at=target
    )
    assert first.status_code == 201, first.text

    second = _book(
        api_client, client_b_headers, pet_id=seeded_db["pet_b"].id, vet_id=vet_id, starts_at=target
    )
    assert second.status_code == 409, second.text
    assert db_session.query(Appointment).count() == 1


def test_the_second_booking_never_returns_a_500(api_client, seeded_db, client_a_headers, client_b_headers):
    """Spelled out separately because a 500 here is the failure PROJECT_PLAN names."""
    vet_id = seeded_db["vet"].id
    day = _business_day()
    target = _slots(api_client, client_a_headers, vet_id, day)[0]["starts_at"]
    _book(api_client, client_a_headers, pet_id=seeded_db["pet_a"].id, vet_id=vet_id, starts_at=target)

    second = _book(
        api_client, client_b_headers, pet_id=seeded_db["pet_b"].id, vet_id=vet_id, starts_at=target
    )
    assert second.status_code < 500
    assert "detail" in second.json()


def test_a_cancelled_slot_can_be_rebooked_over_http(
    api_client, seeded_db, client_a_headers, client_b_headers
):
    vet_id = seeded_db["vet"].id
    day = _business_day()
    target = _slots(api_client, client_a_headers, vet_id, day)[0]["starts_at"]

    created = _book(
        api_client, client_a_headers, pet_id=seeded_db["pet_a"].id, vet_id=vet_id, starts_at=target
    ).json()
    api_client.post(f"/appointments/{created['id']}/cancel", headers=client_a_headers)

    rebooked = _book(
        api_client, client_b_headers, pet_id=seeded_db["pet_b"].id, vet_id=vet_id, starts_at=target
    )
    assert rebooked.status_code == 201, rebooked.text


# ---------------------------------------------------------------------------
# Reading and scope
# ---------------------------------------------------------------------------


@pytest.fixture()
def two_appointments(api_client, seeded_db, client_a_headers, client_b_headers):
    """One appointment for each client, with the same vet."""
    vet_id = seeded_db["vet"].id
    day = _business_day()
    slots = _slots(api_client, client_a_headers, vet_id, day)
    a = _book(
        api_client, client_a_headers, pet_id=seeded_db["pet_a"].id, vet_id=vet_id, starts_at=slots[0]["starts_at"]
    )
    b = _book(
        api_client, client_b_headers, pet_id=seeded_db["pet_b"].id, vet_id=vet_id, starts_at=slots[1]["starts_at"]
    )
    assert a.status_code == 201 and b.status_code == 201
    return {"a": a.json(), "b": b.json()}


def test_a_client_sees_only_their_own_appointments(api_client, two_appointments, client_a_headers):
    body = api_client.get("/appointments", headers=client_a_headers).json()
    assert [row["id"] for row in body] == [two_appointments["a"]["id"]]


def test_a_vet_sees_their_own_schedule(api_client, two_appointments, vet_headers):
    body = api_client.get("/appointments", headers=vet_headers).json()
    assert {row["id"] for row in body} == {
        two_appointments["a"]["id"],
        two_appointments["b"]["id"],
    }


def test_another_vet_sees_an_empty_schedule(api_client, two_appointments, other_vet, login, db_session):
    headers = login("vet2@test.local", "vet2")
    assert api_client.get("/appointments", headers=headers).json() == []


def test_an_admin_sees_every_appointment(api_client, two_appointments, admin_headers):
    body = api_client.get("/appointments", headers=admin_headers).json()
    assert len(body) == 2


def test_a_client_cannot_widen_the_list_with_vet_id(api_client, two_appointments, client_a_headers, seeded_db):
    """Same rule as pets_visible_to: a filter narrows, it never widens."""
    body = api_client.get(
        "/appointments", params={"vet_id": seeded_db["vet"].id}, headers=client_a_headers
    ).json()
    assert [row["id"] for row in body] == [two_appointments["a"]["id"]]


def test_a_client_cannot_widen_the_list_with_pet_id(api_client, two_appointments, client_a_headers, seeded_db):
    body = api_client.get(
        "/appointments", params={"pet_id": seeded_db["pet_b"].id}, headers=client_a_headers
    ).json()
    assert body == []


def test_the_list_can_be_filtered_by_status(api_client, two_appointments, client_a_headers):
    api_client.post(f"/appointments/{two_appointments['a']['id']}/cancel", headers=client_a_headers)
    assert api_client.get(
        "/appointments", params={"status": "CONFIRMED"}, headers=client_a_headers
    ).json() == []
    cancelled = api_client.get(
        "/appointments", params={"status": "CANCELLED"}, headers=client_a_headers
    ).json()
    assert len(cancelled) == 1


def test_reading_another_clients_appointment_is_403(api_client, two_appointments, client_b_headers):
    response = api_client.get(
        f"/appointments/{two_appointments['a']['id']}", headers=client_b_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not your appointment"


def test_reading_an_unknown_appointment_is_404(api_client, seeded_db, client_a_headers):
    response = api_client.get("/appointments/9999", headers=client_a_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Appointment not found"


def test_a_vet_cannot_read_a_colleagues_appointment(api_client, two_appointments, other_vet, login):
    headers = login("vet2@test.local", "vet2")
    response = api_client.get(f"/appointments/{two_appointments['a']['id']}", headers=headers)
    assert response.status_code == 403


def test_an_admin_can_read_any_appointment(api_client, two_appointments, admin_headers):
    assert api_client.get(
        f"/appointments/{two_appointments['a']['id']}", headers=admin_headers
    ).status_code == 200


# ---------------------------------------------------------------------------
# Cancelling
# ---------------------------------------------------------------------------


def test_a_client_can_only_cancel_their_own_appointment(api_client, two_appointments, client_b_headers, db_session):
    """PROJECT_PLAN section 9's fifth test."""
    response = api_client.post(
        f"/appointments/{two_appointments['a']['id']}/cancel", headers=client_b_headers
    )
    assert response.status_code == 403
    row = db_session.get(Appointment, two_appointments["a"]["id"])
    db_session.refresh(row)
    assert row.status is AppointmentStatus.CONFIRMED


def test_the_assigned_vet_can_cancel(api_client, two_appointments, vet_headers):
    response = api_client.post(
        f"/appointments/{two_appointments['a']['id']}/cancel", headers=vet_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_an_admin_can_cancel(api_client, two_appointments, admin_headers):
    assert api_client.post(
        f"/appointments/{two_appointments['a']['id']}/cancel", headers=admin_headers
    ).status_code == 200


def test_cancelling_twice_is_409(api_client, two_appointments, client_a_headers):
    path = f"/appointments/{two_appointments['a']['id']}/cancel"
    assert api_client.post(path, headers=client_a_headers).status_code == 200
    second = api_client.post(path, headers=client_a_headers)
    assert second.status_code == 409
    assert "already cancelled" in second.json()["detail"]


def test_cancelling_a_past_appointment_is_409(api_client, db_session, seeded_db, client_a_headers):
    appointment = _insert_appointment(
        db_session,
        pet=seeded_db["pet_a"],
        vet=seeded_db["vet"],
        starts_at=now_utc() - timedelta(days=1),
    )
    response = api_client.post(f"/appointments/{appointment.id}/cancel", headers=client_a_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Appointment has already started"


def test_a_client_cannot_cancel_inside_the_cutoff(api_client, db_session, seeded_db, client_a_headers):
    """One hour away, cutoff is two. The clinic has already prepared for this."""
    appointment = _insert_appointment(
        db_session,
        pet=seeded_db["pet_a"],
        vet=seeded_db["vet"],
        starts_at=now_utc() + timedelta(hours=1),
    )
    response = api_client.post(f"/appointments/{appointment.id}/cancel", headers=client_a_headers)
    assert response.status_code == 409
    assert "within 2 hours" in response.json()["detail"]
    db_session.refresh(appointment)
    assert appointment.status is AppointmentStatus.CONFIRMED


def test_a_vet_may_cancel_inside_the_cutoff(api_client, db_session, seeded_db, vet_headers):
    """The other half of the pair. Staff are exempt -- someone phoned reception."""
    appointment = _insert_appointment(
        db_session,
        pet=seeded_db["pet_a"],
        vet=seeded_db["vet"],
        starts_at=now_utc() + timedelta(hours=1),
    )
    response = api_client.post(f"/appointments/{appointment.id}/cancel", headers=vet_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"


def test_a_client_may_cancel_outside_the_cutoff(api_client, db_session, seeded_db, client_a_headers):
    appointment = _insert_appointment(
        db_session,
        pet=seeded_db["pet_a"],
        vet=seeded_db["vet"],
        starts_at=now_utc() + timedelta(hours=5),
    )
    assert api_client.post(
        f"/appointments/{appointment.id}/cancel", headers=client_a_headers
    ).status_code == 200


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def _set_status(api_client, headers, appointment_id, value):
    return api_client.post(
        f"/appointments/{appointment_id}/status", json={"status": value}, headers=headers
    )


def test_a_vet_marks_an_appointment_completed(api_client, two_appointments, vet_headers):
    response = _set_status(api_client, vet_headers, two_appointments["a"]["id"], "COMPLETED")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMPLETED"


def test_a_client_cannot_change_status(api_client, two_appointments, client_a_headers, db_session):
    response = _set_status(api_client, client_a_headers, two_appointments["a"]["id"], "COMPLETED")
    assert response.status_code == 403
    row = db_session.get(Appointment, two_appointments["a"]["id"])
    db_session.refresh(row)
    assert row.status is AppointmentStatus.CONFIRMED


def test_a_cancelled_appointment_cannot_be_reconfirmed(api_client, two_appointments, vet_headers, client_a_headers):
    """Terminal means terminal -- another client may hold that slot by now."""
    api_client.post(f"/appointments/{two_appointments['a']['id']}/cancel", headers=client_a_headers)
    response = _set_status(api_client, vet_headers, two_appointments["a"]["id"], "CONFIRMED")
    assert response.status_code == 409
    assert "Cannot change status" in response.json()["detail"]


def test_a_completed_appointment_is_terminal(api_client, two_appointments, vet_headers):
    _set_status(api_client, vet_headers, two_appointments["a"]["id"], "COMPLETED")
    assert _set_status(
        api_client, vet_headers, two_appointments["a"]["id"], "CANCELLED"
    ).status_code == 409


def test_setting_the_status_it_already_has_is_409(api_client, two_appointments, vet_headers):
    response = _set_status(api_client, vet_headers, two_appointments["a"]["id"], "CONFIRMED")
    assert response.status_code == 409
    assert "already confirmed" in response.json()["detail"]


def test_an_unknown_status_is_422(api_client, two_appointments, vet_headers):
    assert _set_status(
        api_client, vet_headers, two_appointments["a"]["id"], "NAPPING"
    ).status_code == 422


def test_a_vet_cannot_complete_a_colleagues_appointment(api_client, two_appointments, other_vet, login):
    headers = login("vet2@test.local", "vet2")
    assert _set_status(api_client, headers, two_appointments["a"]["id"], "COMPLETED").status_code == 403


# ---------------------------------------------------------------------------
# Vets, availability and time off
# ---------------------------------------------------------------------------


def test_listing_vets_shows_names_and_no_account_details(api_client, seeded_db, client_a_headers):
    response = api_client.get("/vets", headers=client_a_headers)
    assert response.status_code == 200
    body = response.json()
    assert [v["full_name"] for v in body] == ["Dr. Test"]
    assert "hashed_password" not in response.text
    assert "email" not in body[0]
    assert "license_no" not in body[0]


def test_a_deactivated_vet_is_not_listed(api_client, db_session, seeded_db, client_a_headers):
    seeded_db["vet_user"].is_active = False
    db_session.commit()
    assert api_client.get("/vets", headers=client_a_headers).json() == []


def test_reading_availability_reports_the_clinic_timezone(api_client, seeded_db, client_a_headers):
    body = api_client.get(
        f"/vets/{seeded_db['vet'].id}/availability", headers=client_a_headers
    ).json()
    assert body["timezone"] == "Asia/Beirut"
    assert len(body["availability"]) == 5
    assert body["availability"][0]["start_time"] == "09:00:00"
    assert body["time_off"] == []


def test_a_vet_can_replace_their_own_availability(api_client, seeded_db, vet_headers):
    response = api_client.put(
        f"/vets/{seeded_db['vet'].id}/availability",
        json=[
            {"weekday": 0, "start_time": "08:00:00", "end_time": "12:00:00", "slot_minutes": 20}
        ],
        headers=vet_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["slot_minutes"] == 20


def test_a_vet_cannot_edit_a_colleagues_availability(api_client, other_vet, vet_headers):
    response = api_client.put(
        f"/vets/{other_vet.id}/availability",
        json=[{"weekday": 0, "start_time": "09:00:00", "end_time": "17:00:00"}],
        headers=vet_headers,
    )
    assert response.status_code == 403


def test_an_admin_can_edit_any_vets_availability(api_client, other_vet, admin_headers):
    assert api_client.put(
        f"/vets/{other_vet.id}/availability",
        json=[{"weekday": 0, "start_time": "09:00:00", "end_time": "17:00:00"}],
        headers=admin_headers,
    ).status_code == 200


def test_a_client_cannot_edit_availability(api_client, seeded_db, client_a_headers):
    assert api_client.put(
        f"/vets/{seeded_db['vet'].id}/availability",
        json=[{"weekday": 0, "start_time": "09:00:00", "end_time": "17:00:00"}],
        headers=client_a_headers,
    ).status_code == 403


def test_overlapping_availability_blocks_are_rejected(api_client, seeded_db, admin_headers):
    """What keeps the slot grid unambiguous -- see _reject_overlaps."""
    response = api_client.put(
        f"/vets/{seeded_db['vet'].id}/availability",
        json=[
            {"weekday": 1, "start_time": "09:00:00", "end_time": "13:00:00"},
            {"weekday": 1, "start_time": "12:00:00", "end_time": "17:00:00"},
        ],
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert "Overlapping" in response.json()["detail"]


def test_two_blocks_on_one_weekday_that_do_not_overlap_are_fine(api_client, seeded_db, admin_headers):
    """A morning and an afternoon list with lunch between them."""
    response = api_client.put(
        f"/vets/{seeded_db['vet'].id}/availability",
        json=[
            {"weekday": 1, "start_time": "09:00:00", "end_time": "12:00:00"},
            {"weekday": 1, "start_time": "13:00:00", "end_time": "17:00:00"},
        ],
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 2


def test_availability_with_end_before_start_is_422(api_client, seeded_db, admin_headers):
    assert api_client.put(
        f"/vets/{seeded_db['vet'].id}/availability",
        json=[{"weekday": 0, "start_time": "17:00:00", "end_time": "09:00:00"}],
        headers=admin_headers,
    ).status_code == 422


def test_a_slot_longer_than_the_working_block_is_422(api_client, seeded_db, admin_headers):
    assert api_client.put(
        f"/vets/{seeded_db['vet'].id}/availability",
        json=[
            {"weekday": 0, "start_time": "09:00:00", "end_time": "10:00:00", "slot_minutes": 120}
        ],
        headers=admin_headers,
    ).status_code == 422


def test_a_vet_can_book_time_off_and_it_removes_slots(api_client, seeded_db, vet_headers, client_a_headers):
    vet_id = seeded_db["vet"].id
    day = _business_day()
    before = len(_slots(api_client, client_a_headers, vet_id, day))

    response = api_client.post(
        f"/vets/{vet_id}/time-off",
        json={
            "starts_at": local_to_utc(day, time(9, 0)).isoformat(),
            "ends_at": local_to_utc(day, time(11, 0)).isoformat(),
            "reason": "Dentist",
        },
        headers=vet_headers,
    )
    assert response.status_code == 201, response.text
    assert len(_slots(api_client, client_a_headers, vet_id, day)) == before - 4


def test_deleting_time_off_restores_the_slots(api_client, seeded_db, vet_headers, client_a_headers):
    vet_id = seeded_db["vet"].id
    day = _business_day()
    before = len(_slots(api_client, client_a_headers, vet_id, day))
    created = api_client.post(
        f"/vets/{vet_id}/time-off",
        json={
            "starts_at": local_to_utc(day, time(9, 0)).isoformat(),
            "ends_at": local_to_utc(day, time(11, 0)).isoformat(),
        },
        headers=vet_headers,
    ).json()

    assert api_client.delete(
        f"/vets/{vet_id}/time-off/{created['id']}", headers=vet_headers
    ).status_code == 204
    assert len(_slots(api_client, client_a_headers, vet_id, day)) == before


def test_deleting_another_vets_time_off_is_404(api_client, seeded_db, other_vet, vet_headers, admin_headers):
    """Named through the caller's own vet_id in the path -- still not theirs."""
    day = _business_day()
    created = api_client.post(
        f"/vets/{other_vet.id}/time-off",
        json={
            "starts_at": local_to_utc(day, time(9, 0)).isoformat(),
            "ends_at": local_to_utc(day, time(11, 0)).isoformat(),
        },
        headers=admin_headers,
    ).json()

    response = api_client.delete(
        f"/vets/{seeded_db['vet'].id}/time-off/{created['id']}", headers=vet_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Time off not found"


def test_a_client_cannot_create_time_off(api_client, seeded_db, client_a_headers):
    day = _business_day()
    assert api_client.post(
        f"/vets/{seeded_db['vet'].id}/time-off",
        json={
            "starts_at": local_to_utc(day, time(9, 0)).isoformat(),
            "ends_at": local_to_utc(day, time(11, 0)).isoformat(),
        },
        headers=client_a_headers,
    ).status_code == 403


def test_time_off_ending_before_it_starts_is_422(api_client, seeded_db, vet_headers):
    day = _business_day()
    assert api_client.post(
        f"/vets/{seeded_db['vet'].id}/time-off",
        json={
            "starts_at": local_to_utc(day, time(11, 0)).isoformat(),
            "ends_at": local_to_utc(day, time(9, 0)).isoformat(),
        },
        headers=vet_headers,
    ).status_code == 422


def test_availability_for_an_unknown_vet_is_404(api_client, seeded_db, client_a_headers):
    assert api_client.get("/vets/9999/availability", headers=client_a_headers).status_code == 404


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/appointments"),
        ("get", "/appointments/slots"),
        ("post", "/appointments"),
        ("get", "/appointments/1"),
        ("post", "/appointments/1/cancel"),
        ("post", "/appointments/1/status"),
        ("get", "/vets"),
        ("get", "/vets/1/availability"),
        ("put", "/vets/1/availability"),
        ("post", "/vets/1/time-off"),
        ("delete", "/vets/1/time-off/1"),
    ],
)
def test_every_endpoint_requires_a_token(api_client, seeded_db, method, path):
    response = getattr(api_client, method)(path)
    assert response.status_code == 401, f"{method.upper()} {path} -> {response.status_code}"
