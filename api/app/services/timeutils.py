"""Clinic-local time <-> UTC. The one place this project does timezone maths. (Phase 4)

Three facts about this stack drive everything in this file. All three were
measured against api/.venv, not assumed:

1. **SQLite silently discards the offset on write.** Storing an aware
   ``2026-09-01 12:00+03:00`` writes the string ``2026-09-01 12:00:00.000000``.
   It keeps the *wall clock*, not the instant.

2. **So ``uq_vet_active_slot`` protects nothing on its own.** Booking ``09:00Z``
   and then the identical instant written as ``12:00+03:00`` produced two rows,
   because the unique index compares the stored strings. Normalising to UTC
   before the value reaches the Session is what makes layer 1 real -- it is not
   a tidiness nicety.

3. **Values read back are naive.** ``row.starts_at.tzinfo is None``, so
   ``row.starts_at >= datetime.now(timezone.utc)`` raises TypeError. Anything
   compared in Python goes through ``ensure_utc`` first. SQL-level ``WHERE``
   comparisons against aware values do work, and are preferred.

Nothing here touches the ORM or raises HTTPException (CLAUDE.md's layering rule).
"""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.config import settings

# The clinic's wall clock. vet_availability rows are read in this zone.
CLINIC_TZ = ZoneInfo(settings.clinic_timezone)


def ensure_utc(value: datetime) -> datetime:
    """Aware UTC, whatever came in.

    A naive value is *assumed* to already be UTC rather than rejected, because
    that is exactly what SQLite hands back for a DateTime(timezone=True) column
    (fact 3 above) and every write goes through ``to_utc`` first. An aware value
    in any other zone is converted, which is fact 2's fix.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_utc(value: datetime) -> datetime:
    """Alias for ensure_utc, named for the write path.

    Call this on every datetime heading for the database. The two names are the
    same function on purpose: reading and writing need identical normalisation,
    and one implementation cannot drift from the other.
    """
    return ensure_utc(value)


def utc_to_clinic(value: datetime) -> datetime:
    """A stored instant as the clinic's wall clock.

    Not used in any response -- the API speaks UTC and the Phase 5 frontend
    converts for display. This is for log lines, PHASE_4.md's worked examples and
    manual QA, where "07:00Z" is much harder to sanity-check than "10:00".
    """
    return ensure_utc(value).astimezone(CLINIC_TZ)


def local_to_utc(day: date, wall: time) -> datetime | None:
    """A clinic-local wall clock on a given date, as a UTC instant.

    Returns None when that local time does not exist -- the hour skipped on the
    DST spring-forward day. Existence is checked by round-tripping rather than by
    consulting a transition table: if converting to UTC and back does not land on
    the time we asked for, the time was never on the clinic's clock.

    Asia/Beirut changes at 00:00 local, so the gap is 00:00-00:59 and no
    plausible clinic hours reach it. The guard costs one comparison and means
    slot generation stays correct if the clinic timezone setting ever changes to
    a zone that transitions during the working day.
    """
    local = datetime.combine(day, wall, tzinfo=CLINIC_TZ)
    as_utc = local.astimezone(timezone.utc)
    if as_utc.astimezone(CLINIC_TZ) != local:
        return None
    return as_utc


def now_utc() -> datetime:
    """Aware UTC now. One spelling, so tests have one thing to reason about."""
    return datetime.now(timezone.utc)
