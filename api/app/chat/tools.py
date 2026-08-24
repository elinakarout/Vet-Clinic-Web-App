"""build_tools(current_user, db) -- tool closures bound to the authenticated user. (Phase 7)

**The one rule that matters here** (root CLAUDE.md, PROJECT_PLAN.md sec 7 "The
security rule that matters most"): the user's identity comes from the JWT, never
from the conversation. Every tool below is a closure over ``current_user``, and
no tool schema has a ``user_id``, ``client_id`` or ``owner_id`` parameter. If one
did, "list the pets belonging to client 7" would work, and the model would help
enthusiastically. Closing over the authenticated user makes it impossible by
construction rather than by remembering to check.

*Resource* ids are a different thing and are accepted: ``pet_id`` and
``appointment_id`` come from the model, and are then re-checked through the same
``deps.get_owned_pet`` / ``deps.get_owned_appointment`` dependencies the HTTP
routes use. A model that guesses an id it should not see gets the same 403 the
API would give, converted here into a sentence.

**Nothing here books, and nothing here cancels.** ``propose_appointment`` and
``propose_cancellation`` return structured data that routers/chat.py emits as a
Confirm card; the click calls the ordinary REST endpoints. PROJECT_PLAN.md sec 7's
tool table gave the chatbot a real ``cancel_appointment``; that is the one entry
this module deliberately does not implement -- see PHASE_7.md decision 6.

Tool docstrings are the model's only guide to when to call each one, and
PROJECT_PLAN.md sec 7 calls them "the single biggest lever on chatbot quality".
They are written for the model, not for a Python caller, which is why they read
like instructions.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_owned_appointment, get_owned_pet
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentStatus,
    Pet,
    Role,
    User,
    Vaccination,
    VetProfile,
)
from app.rag.retrieve import search_knowledge
from app.services import scheduling
from app.services.pets import pets_visible_to
from app.services.timeutils import CLINIC_TZ, ensure_utc, now_utc, utc_to_clinic

logger = logging.getLogger(__name__)

# How far ahead find_available_slots looks when the user has not said. Two weeks
# is long enough to find something for "sometime soon" and short enough that the
# rendered list stays readable to a model with a token budget.
_DEFAULT_SEARCH_DAYS = 14
# Cap on what one tool call renders back to the model. A vet with 30-minute slots
# over two weeks has ~160 openings; all of them would drown the reply.
_MAX_SLOTS_RENDERED = 24


# ---------------------------------------------------------------------------
# The tool registry
# ---------------------------------------------------------------------------


@dataclass
class Tool:
    """One callable the model may invoke, with the JSON Schema describing it."""

    name: str
    description: str
    parameters: dict[str, Any]
    label: str  # "Checking availability..." -- shown in the UI during the call
    fn: Callable[..., str]

    def schema(self) -> dict[str, Any]:
        """The OpenAI-compatible function-tool shape both gateways accept."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolRegistry:
    """The tools built for one request, plus whatever they proposed.

    Built fresh per request because the closures capture that request's user and
    Session. Reusing a registry across users is the exact bug this design exists
    to prevent, so it is never cached.
    """

    tools: dict[str, Tool] = field(default_factory=dict)
    # Appended to by propose_appointment / propose_cancellation. The router drains
    # this after the model's turn and emits one `proposal` event per entry.
    proposals: list[dict[str, Any]] = field(default_factory=list)
    used: list[str] = field(default_factory=list)

    def add(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self.tools.values()]

    def label_for(self, name: str) -> str:
        tool = self.tools.get(name)
        return tool.label if tool else "Working..."

    def call(self, name: str, arguments: str | dict[str, Any] | None) -> str:
        """Run one tool call and return what the model should see.

        Never raises. A tool that blows up must come back as a sentence the model
        can react to -- an exception here would abort a half-streamed reply, and
        the user would watch the message stop mid-word.
        """
        tool = self.tools.get(name)
        if tool is None:
            return f"There is no tool called {name!r}."

        if isinstance(arguments, str):
            try:
                # An empty string is what a no-argument call looks like on the
                # wire; json.loads("") raises, so it is handled before parsing.
                parsed = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return "Those arguments were not valid JSON. Please call the tool again."
        else:
            parsed = arguments or {}

        if not isinstance(parsed, dict):
            return "Tool arguments must be a JSON object."

        self.used.append(name)
        try:
            return tool.fn(**parsed)
        except TypeError as exc:
            # Wrong or missing argument names. Telling the model what went wrong
            # lets it retry; a traceback would just end the turn.
            return f"That call did not match the tool's parameters ({exc}). Please try again."
        except Exception:
            logger.exception("Chat tool %s failed", name)
            return (
                "Something went wrong looking that up. Tell the user you could not "
                "retrieve it and suggest they call the clinic."
            )


# ---------------------------------------------------------------------------
# Formatting helpers -- everything the model reads is in CLINIC time
# ---------------------------------------------------------------------------


def _clinic(value: datetime) -> str:
    """A stored UTC instant as a human sentence in the clinic's zone.

    Never UTC. The model repeats these strings back to the user, and "07:00" for
    a 10:00 Beirut appointment is the kind of error nobody notices until someone
    arrives three hours early.
    """
    return utc_to_clinic(value).strftime("%A %d %B %Y at %H:%M")


def _iso(value: datetime) -> str:
    """The exact UTC instant, for handing back to propose_appointment.

    Paired with _clinic() in every slot listing: the model shows the human one to
    the user and passes this one to the next tool. FRONTEND.md's rule that a
    starts_at is never reconstructed applies to the model too.
    """
    return ensure_utc(value).isoformat().replace("+00:00", "Z")


def _describe_pet(pet: Pet) -> str:
    bits = [f"#{pet.id} {pet.name} -- {pet.species}"]
    if pet.breed:
        bits.append(pet.breed)
    if pet.date_of_birth:
        years = (date.today() - pet.date_of_birth).days // 365
        bits.append(f"{years} year(s) old" if years else "under a year old")
    if pet.sex and pet.sex.value != "UNKNOWN":
        bits.append(pet.sex.value.lower())
    if pet.weight_kg:
        bits.append(f"{pet.weight_kg:g} kg")
    return ", ".join(bits)


def _client_profile_id(user: User) -> int | None:
    """The caller's client_profiles.id, or None if they are staff.

    pets.owner_id is a client_profiles.id, never a users.id -- the off-by-one
    table that root CLAUDE.md warns about twice.
    """
    if user.role is not Role.CLIENT:
        return None
    profile = user.client_profile
    return profile.id if profile is not None else None


_STAFF_HAS_NO_PETS = (
    "This account is clinic staff, not a client, so it has no pets or appointments "
    "of its own on file. Tell the user you can still answer questions about the "
    "clinic, but that pet and booking tools only work for client accounts."
)


# ---------------------------------------------------------------------------
# build_tools
# ---------------------------------------------------------------------------


def build_tools(current_user: User, db: Session) -> ToolRegistry:
    """The seven tools, each closed over this request's authenticated user.

    ``current_user`` comes from ``deps.get_current_user``, which decoded the
    bearer token and re-read the row. Nothing the model says can change it.
    """
    registry = ToolRegistry()

    # -- 1. Knowledge base ---------------------------------------------------

    def search_clinic_knowledge(query: str) -> str:
        passages = search_knowledge(query, k=settings.retrieval_k)
        if not passages:
            # PHASE_6.md: an empty result is a normal outcome, not an error, and
            # the whole point of the calibrated similarity floor. Saying so is
            # better than the model reciting the five least-bad chunks.
            return (
                "The clinic knowledge base has nothing relevant to that. Tell the user "
                "you do not have that information and suggest they call the clinic. Do "
                "not guess at prices, opening hours, policies or vaccination intervals."
            )
        blocks = []
        for passage in passages:
            attribution = f" (source: {passage.source_url})" if passage.source_url else ""
            blocks.append(f"[{passage.title}]{attribution}\n{passage.text}")
        return "\n\n".join(blocks)

    registry.add(
        Tool(
            name="search_clinic_knowledge",
            description=(
                "Search the clinic's knowledge base for information about services, prices, "
                "opening hours, booking and cancellation policy, vaccination schedules, "
                "post-surgery care, what to bring to a first visit, emergency guidance, and "
                "general pet health. Use this whenever the user asks a factual question about "
                "the clinic or about pet care, BEFORE answering. If it returns nothing "
                "relevant, say you do not have that information -- never guess."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for, in natural language.",
                    }
                },
                "required": ["query"],
            },
            label="Checking the clinic's information...",
            fn=search_clinic_knowledge,
        )
    )

    # -- 2. The caller's pets ------------------------------------------------

    def list_my_pets() -> str:
        if _client_profile_id(current_user) is None:
            return _STAFF_HAS_NO_PETS
        # pets_visible_to already pins a CLIENT to their own client_profile.id and
        # ignores any widening argument. Reusing it means this tool cannot drift
        # away from the rule GET /pets enforces.
        pets = list(db.scalars(pets_visible_to(current_user)))
        if not pets:
            return "This user has no pets registered yet. They can add one from the Pets page."
        return "The user's pets:\n" + "\n".join(f"- {_describe_pet(p)}" for p in pets)

    registry.add(
        Tool(
            name="list_my_pets",
            description=(
                "List the pets belonging to the user you are talking to, with their id, "
                "species, breed and age. Call this before asking the user which pet they mean "
                "-- you can already see them, so asking is a worse experience. You need a pet "
                "id from here before you can check vaccinations or propose an appointment."
            ),
            parameters={"type": "object", "properties": {}},
            label="Looking up your pets...",
            fn=list_my_pets,
        )
    )

    # -- 3. Vaccination status -----------------------------------------------

    def get_pet_vaccination_status(pet_id: int) -> str:
        try:
            # The same dependency GET /pets/{id} uses, called directly the way
            # routers/appointments.py:create_appointment calls it. A pet id the
            # model invented gets the API's own 404/403, as a sentence.
            pet = get_owned_pet(pet_id=int(pet_id), current_user=current_user, db=db)
        except HTTPException as exc:
            return f"Cannot look that pet up: {exc.detail}."

        rows = list(
            db.scalars(
                select(Vaccination)
                .where(Vaccination.pet_id == pet.id)
                .order_by(Vaccination.given_at.desc())
            )
        )
        if not rows:
            return (
                f"{pet.name} has no vaccination history recorded at this clinic. That does not "
                "mean they are unvaccinated -- records from another practice may not be here. "
                "Search the knowledge base for the schedule for a "
                f"{pet.species.lower()} and suggest booking to review it."
            )

        today = date.today()
        lines = []
        for row in rows:
            line = f"- {row.vaccine_name}: given {row.given_at.isoformat()}"
            if row.due_at is None:
                line += ", no next dose recorded"
            elif row.due_at < today:
                line += f", next dose was due {row.due_at.isoformat()} (OVERDUE)"
            else:
                line += f", next dose due {row.due_at.isoformat()}"
            lines.append(line)
        return f"Vaccination record for {pet.name} (today is {today.isoformat()}):\n" + "\n".join(lines)

    registry.add(
        Tool(
            name="get_pet_vaccination_status",
            description=(
                "Show one pet's vaccination history and what is due or overdue. Use it when "
                "the user asks about shots, boosters or whether a pet is up to date. Get the "
                "pet id from list_my_pets first. Report what the record says; do not infer "
                "which vaccine a pet ought to have -- search the knowledge base for that."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "integer",
                        "description": "The pet's id, as returned by list_my_pets.",
                    }
                },
                "required": ["pet_id"],
            },
            label="Checking vaccination records...",
            fn=get_pet_vaccination_status,
        )
    )

    # -- 4. Free slots -------------------------------------------------------

    def _bookable_vets(vet_id: int | None) -> list[VetProfile]:
        """Active vets, or the one asked for. Mirrors routers/vets.py:list_vets."""
        stmt = (
            select(VetProfile)
            .join(User, VetProfile.user_id == User.id)
            .where(User.is_active.is_(True))
            .order_by(VetProfile.full_name, VetProfile.id)
        )
        if vet_id is not None:
            stmt = stmt.where(VetProfile.id == vet_id)
        return list(db.scalars(stmt))

    def find_available_slots(
        reason: str,
        preferred_days: str | None = None,
        vet_id: int | None = None,
    ) -> str:
        vets = _bookable_vets(int(vet_id) if vet_id is not None else None)
        if not vets:
            if vet_id is not None:
                return "There is no vet with that id taking appointments."
            return "No vets are currently taking appointments. Suggest the user call the clinic."

        # A clinic-local window: the caller means "Tuesday" on the clinic's
        # calendar, which is exactly what generate_slots takes.
        today = utc_to_clinic(now_utc()).date()
        span = min(_DEFAULT_SEARCH_DAYS, settings.max_slot_range_days)
        date_from, date_to = today, today + timedelta(days=span)

        found: list[tuple[scheduling.Slot, VetProfile]] = []
        for vet in vets:
            try:
                slots = scheduling.generate_slots(
                    db, vet_id=vet.id, date_from=date_from, date_to=date_to
                )
            except scheduling.VetNotFound:
                continue
            found.extend((slot, vet) for slot in slots)

        if not found:
            return (
                f"No free appointments between {date_from.isoformat()} and "
                f"{date_to.isoformat()}. Tell the user and suggest they call the clinic."
            )

        found.sort(key=lambda pair: (pair[0].starts_at, pair[1].full_name))
        shown = found[:_MAX_SLOTS_RENDERED]

        header = (
            f"Free appointments for '{reason}' between {date_from.isoformat()} and "
            f"{date_to.isoformat()}, in clinic local time"
        )
        if preferred_days:
            # Passed through rather than parsed: the model reads the list and
            # picks. Free-text day parsing here would be a second, worse
            # scheduler that disagrees with generate_slots at the edges.
            header += f". The user asked for: {preferred_days}. Offer the closest matches"
        if len(found) > len(shown):
            header += f". Showing the first {len(shown)} of {len(found)}"

        lines = [
            f"- {_clinic(slot.starts_at)} with {vet.full_name} (vet_id={vet.id}, "
            f"{slot.slot_minutes} min) slot_start={_iso(slot.starts_at)}"
            for slot, vet in shown
        ]
        return (
            f"{header}:\n"
            + "\n".join(lines)
            + "\n\nWhen proposing one, pass slot_start back EXACTLY as printed above."
        )

    registry.add(
        Tool(
            name="find_available_slots",
            description=(
                "Find real free appointment slots on the vets' calendars over the next two "
                "weeks. Call this before suggesting any time -- never invent one, and never "
                "assume a time is free because it sounds like working hours. Returns each "
                "slot's exact slot_start value, which propose_appointment requires verbatim."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why the pet is coming in, e.g. 'annual vaccination'.",
                    },
                    "preferred_days": {
                        "type": "string",
                        "description": (
                            "What the user said about timing in their own words, e.g. "
                            "'next Tuesday' or 'weekday mornings'. Optional."
                        ),
                    },
                    "vet_id": {
                        "type": "integer",
                        "description": (
                            "Restrict to one vet. Omit unless the user named a vet; omitting "
                            "it searches every vet, which finds more."
                        ),
                    },
                },
                "required": ["reason"],
            },
            label="Checking availability...",
            fn=find_available_slots,
        )
    )

    # -- 5. Propose a booking (writes NOTHING) -------------------------------

    def propose_appointment(
        pet_id: int,
        vet_id: int,
        slot_start: str,
        reason: str | None = None,
    ) -> str:
        try:
            pet = get_owned_pet(pet_id=int(pet_id), current_user=current_user, db=db)
        except HTTPException as exc:
            return f"Cannot propose that: {exc.detail}."

        try:
            parsed = datetime.fromisoformat(str(slot_start).replace("Z", "+00:00"))
        except ValueError:
            return (
                "slot_start was not a valid timestamp. Copy it exactly as "
                "find_available_slots printed it."
            )
        if parsed.tzinfo is None:
            # Same refusal AppointmentCreate makes, and for the same reason: a
            # naive time is ambiguous by two or three hours depending on season.
            return (
                "slot_start must include a UTC offset. Copy it exactly as "
                "find_available_slots printed it."
            )
        starts_at = ensure_utc(parsed)

        vet = db.get(VetProfile, int(vet_id))
        if vet is None or vet.user is None or not vet.user.is_active:
            return "There is no vet with that id taking appointments."

        # Validate by asking the scheduler whether this is one of its own slots,
        # which is exactly how scheduling.book_appointment validates. Re-checking
        # hours, grid, time-off and the past separately here would be a second
        # implementation that drifts.
        local_day = utc_to_clinic(starts_at).date()
        try:
            slots = scheduling.generate_slots(
                db, vet_id=vet.id, date_from=local_day, date_to=local_day
            )
        except scheduling.VetNotFound:
            return "There is no vet with that id taking appointments."

        match = next((s for s in slots if s.starts_at == starts_at), None)
        if match is None:
            return (
                "That time is not a free slot on that vet's calendar any more. Call "
                "find_available_slots again and offer the user a current option."
            )

        # Reaching for a private helper on purpose. The alternative is a second
        # copy of the pet-overlap query here, which would be one more thing to
        # keep in step with scheduling.py. Without the check the card still gets
        # a clean 409 on click -- it just wastes the user's tap.
        if scheduling._pet_is_busy(
            db, pet_id=pet.id, starts_at=match.starts_at, ends_at=match.ends_at
        ):
            return f"{pet.name} already has an appointment overlapping that time."

        proposal = {
            "pet_id": pet.id,
            "pet_name": pet.name,
            "vet_id": vet.id,
            "vet_name": vet.full_name,
            "starts_at": _iso(match.starts_at),
            "ends_at": _iso(match.ends_at),
            "reason": reason,
        }
        registry.proposals.append({"kind": "appointment", "proposal": proposal})
        return (
            f"A confirmation card for {pet.name} with {vet.full_name} on "
            f"{_clinic(match.starts_at)} is now on screen. NOTHING IS BOOKED YET. Tell the "
            "user to tap the card to confirm, and do not claim the appointment is made."
        )

    registry.add(
        Tool(
            name="propose_appointment",
            description=(
                "Put a suggested appointment in front of the user as a confirmation card. "
                "This does NOT book anything -- the user books it by tapping the card. Use a "
                "slot_start copied exactly from find_available_slots. Propose two or three "
                "options by calling this once per option, after confirming which pet and why."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pet_id": {"type": "integer", "description": "From list_my_pets."},
                    "vet_id": {"type": "integer", "description": "From find_available_slots."},
                    "slot_start": {
                        "type": "string",
                        "description": (
                            "The slot_start value from find_available_slots, copied verbatim, "
                            "e.g. 2026-09-01T06:00:00Z. Never construct one yourself."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "description": "Short reason for the visit, shown on the card.",
                    },
                },
                "required": ["pet_id", "vet_id", "slot_start"],
            },
            label="Preparing an appointment...",
            fn=propose_appointment,
        )
    )

    # -- 6. The caller's appointments ----------------------------------------

    def list_my_appointments() -> str:
        if current_user.role is Role.ADMIN:
            # appointments_visible_to shows an ADMIN the whole clinic, which is
            # right for GET /appointments and wrong for a tool called "my
            # appointments" -- nothing leaks, but the model would read the
            # clinic's entire diary back as though it were this user's.
            return _STAFF_HAS_NO_PETS
        # For everyone else appointments_visible_to applies the same "a filter may
        # only narrow" rule as GET /appointments: a CLIENT sees strictly their
        # own, and a VET sees their own schedule -- which is what a vet asking
        # this question actually means.
        stmt = scheduling.appointments_visible_to(current_user).where(
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES)
        )
        now = now_utc()
        upcoming = [row for row in db.scalars(stmt) if ensure_utc(row.starts_at) >= now]
        if not upcoming:
            return "There are no upcoming appointments on this account."

        upcoming.sort(key=lambda row: ensure_utc(row.starts_at))
        lines = []
        for row in upcoming:
            vet = db.get(VetProfile, row.vet_id)
            pet = db.get(Pet, row.pet_id)
            lines.append(
                f"- appointment #{row.id}: {pet.name if pet else 'a pet'} with "
                f"{vet.full_name if vet else 'a vet'} on {_clinic(row.starts_at)}"
                f" ({row.status.value.lower()})"
                + (f" -- {row.reason}" if row.reason else "")
            )
        return "Upcoming appointments:\n" + "\n".join(lines)

    registry.add(
        Tool(
            name="list_my_appointments",
            description=(
                "List the upcoming appointments on the user's account, with their id, pet, "
                "vet and time. Use it when the user asks what they have booked, or before "
                "proposing a cancellation -- you need an appointment id from here."
            ),
            parameters={"type": "object", "properties": {}},
            label="Looking up your appointments...",
            fn=list_my_appointments,
        )
    )

    # -- 7. Propose a cancellation (writes NOTHING) --------------------------

    def propose_cancellation(appointment_id: int) -> str:
        try:
            appointment = get_owned_appointment(
                appointment_id=int(appointment_id), current_user=current_user, db=db
            )
        except HTTPException as exc:
            return f"Cannot cancel that: {exc.detail}."

        if appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
            return f"That appointment is already {appointment.status.value.lower()}."

        starts_at = ensure_utc(appointment.starts_at)
        now = now_utc()
        if starts_at <= now:
            return "That appointment has already started and cannot be cancelled here."

        if current_user.role is Role.CLIENT:
            # Checked here as well as in scheduling.cancel_appointment so the card
            # is never offered for something the confirm click would 409 on. The
            # service call remains the real enforcement.
            cutoff = timedelta(hours=settings.cancellation_cutoff_hours)
            if starts_at - now < cutoff:
                return (
                    f"That appointment starts within {settings.cancellation_cutoff_hours} "
                    "hours, so it cannot be cancelled online. Tell the user to call the clinic."
                )

        pet = db.get(Pet, appointment.pet_id)
        vet = db.get(VetProfile, appointment.vet_id)
        proposal = {
            "appointment_id": appointment.id,
            "pet_id": appointment.pet_id,
            "pet_name": pet.name if pet else "the pet",
            "vet_name": vet.full_name if vet else "the vet",
            "starts_at": _iso(starts_at),
            "ends_at": _iso(appointment.ends_at),
            "reason": appointment.reason,
        }
        registry.proposals.append({"kind": "cancellation", "proposal": proposal})
        return (
            f"A cancellation card for appointment #{appointment.id} on "
            f"{_clinic(starts_at)} is now on screen. NOTHING IS CANCELLED YET. Tell the user "
            "to tap the card to confirm."
        )

    registry.add(
        Tool(
            name="propose_cancellation",
            description=(
                "Put a cancellation in front of the user as a confirmation card. This does "
                "NOT cancel anything -- the user confirms by tapping the card. Get the "
                "appointment id from list_my_appointments first. Checks the clinic's "
                "cancellation cutoff, so it will refuse an appointment that is too close."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "integer",
                        "description": "From list_my_appointments.",
                    }
                },
                "required": ["appointment_id"],
            },
            label="Preparing a cancellation...",
            fn=propose_cancellation,
        )
    )

    return registry
