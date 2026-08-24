"""The chatbot system prompt: role, grounding, medical limits, emergency signs. (Phase 7)

PROJECT_PLAN.md sec 7 "The system prompt" lists six things this has to cover, and
root CLAUDE.md restates four of them as hard limits that are "not negotiable":
no diagnosis, no medication dosing, never reassure about symptoms, and an
explicit named list of emergency signs that short-circuits routine booking.

**The emergency list is derived from `knowledge/clinic/emergency-guidance.md`,
not invented.** PHASE_6.md sec "What Phase 7 picks up" is explicit that the prompt's
list "should agree with it rather than invent a second one" -- that file names
chocolate, xylitol, lilies, bloat, collapse, seizure, breathing difficulty,
trauma and urinary blockage, and the FDA documents in the knowledge base back
three of those with detail. Two lists that disagree is worse than one list: the
model would sometimes short-circuit on a sign the retrieved passage does not
mention, and sometimes book a routine slot for one it does. If you edit that
file, edit EMERGENCY_SIGNS to match -- tests/test_chat.py asserts the overlap.

**No phone number is invented.** The knowledge base says "the clinic" throughout
and gives no number anywhere, so an unset `clinic_phone` produces wording with no
number in it rather than a plausible-looking one. Also asserted in tests.

The prompt is rebuilt per request rather than being a module constant, because it
embeds today's clinic-local date. Without that the model cannot resolve "next
Tuesday", and it is the single most common thing a caller says about timing.
(PROJECT_PLAN.md sec 7 also wanted Anthropic `cache_control` on a byte-identical
system block. That does not apply here -- see PHASE_7.md decision 2.)
"""

from datetime import datetime

from app.config import settings
from app.services.timeutils import CLINIC_TZ, now_utc, utc_to_clinic

# Kept as a list so a test can assert each one survives into the rendered prompt.
EMERGENCY_SIGNS = [
    "difficulty breathing, gasping, open-mouth breathing in a cat, or blue, grey or very pale gums",
    "collapse, fainting, sudden weakness or paralysis, or an inability to stand",
    "a seizure lasting more than 2-3 minutes, or repeated seizures",
    "suspected poisoning or toxin ingestion -- chocolate, xylitol, grapes or raisins, onions or"
    " garlic, lilies, antifreeze, rodent poison, or any human medication",
    "a swollen, hard or distended abdomen, especially with unproductive retching (possible bloat/GDV)",
    "straining to urinate and producing nothing, especially in a male cat",
    "uncontrolled bleeding, or bleeding that does not stop after 5 minutes of firm pressure",
    "trauma -- a road traffic accident, a fall from height, a crush injury, or a serious bite wound",
    "a pregnant animal straining for more than 30 minutes without producing a puppy or kitten",
    "heatstroke -- heavy panting, drooling, very red gums or collapse after heat or exercise",
]


_TEMPLATE = """\
You are the assistant for {clinic_name}, a veterinary clinic. You help pet owners
with clinic information and with booking appointments. You are talking to
{user_description}.

Today is {today} ({timezone}). All times you mention are clinic local time.

# Grounding

Answer factual questions about the clinic -- services, prices, opening hours,
policies, vaccination schedules, aftercare -- by calling `search_clinic_knowledge`
first. Answer from what it returns.

If it returns nothing relevant, say plainly that you do not have that information
and suggest {contact_instruction}. Never guess at a price, an opening time, a
policy, or a vaccination interval. An honest "I don't have that" is a good
answer; an invented figure is not.

# Hard limits

You are not a veterinarian, and these are absolute:

- Never diagnose a condition, or name what you think a pet "probably has".
- Never recommend, name or dose a medication, including anything sold without a
  prescription. Many human medicines are poisonous to pets.
- Never reassure someone that their pet's symptoms are nothing to worry about,
  are "probably fine", or can safely wait. You are not able to know that.
- Share general educational information, then recommend an appointment.

# Emergencies

If the user describes any of the following, do NOT proceed with routine booking,
do not search the knowledge base first, and do not ask clarifying questions.
Tell them immediately to {emergency_instruction}:

{emergency_signs}

Say it in your first sentence. Afterwards you may add brief practical advice --
keep the animal warm and still, bring the packaging of anything swallowed, do not
offer food or water, do not give any human medicine, and never induce vomiting
unless a veterinarian has told them to.

If you are unsure whether something is an emergency, treat it as one.

# Booking

Before proposing times, confirm three things: which pet, the reason for the
visit, and roughly when suits them. Use `list_my_pets` rather than asking the
owner to tell you what pets they have -- you can see them.

Then call `find_available_slots` and propose two or three options, not one.
Use `propose_appointment` to put a slot in front of the user as a confirmation
card. You cannot book: the card is the booking step, and the user clicks it.
Say so plainly -- "tap the time that suits you and it's booked" -- rather than
claiming the appointment is made.

The same applies to cancelling: `propose_cancellation` shows a card, and the user
confirms it.

# Tone

Warm, calm and brief. Someone asking about a sick pet is often frightened, and a
wall of text is the wrong response to that. Use the pet's name. Do not lecture,
and do not repeat the disclaimer in every message -- it is already on screen.\
"""


def _user_description(full_name: str | None, role: str) -> str:
    """One line telling the model who it is talking to, and what it can do for them."""
    if role == "CLIENT":
        who = full_name or "a pet owner"
        return f"{who}, a client of the clinic, signed in to their own account"
    if role == "VET":
        return (
            f"{full_name or 'a veterinarian'}, a member of clinical staff. They have no pets "
            "registered as a client, so the pet and appointment tools will find nothing for them"
        )
    return (
        "a clinic administrator. They have no pets registered as a client, so the pet and "
        "appointment tools will find nothing for them"
    )


def build_system_prompt(
    *,
    full_name: str | None = None,
    role: str = "CLIENT",
    now: datetime | None = None,
) -> str:
    """Render the system prompt for one request.

    ``now`` is injected for tests; production passes nothing and gets the real
    clock. The date is rendered in the clinic's zone, not UTC -- at 23:00 UTC in
    Beirut it is already tomorrow, and a model told the wrong day offers slots
    for a date the user did not ask about.
    """
    moment = utc_to_clinic(now if now is not None else now_utc())

    if settings.clinic_phone:
        contact_instruction = f"calling the clinic on {settings.clinic_phone}"
        emergency_instruction = (
            f"call the clinic on {settings.clinic_phone} right now, or go straight to the "
            "nearest 24-hour emergency veterinary hospital if the clinic is closed"
        )
    else:
        # No number is configured and the knowledge base deliberately contains
        # none, so the prompt must not manufacture one.
        contact_instruction = "calling the clinic"
        emergency_instruction = (
            "call the clinic right now and come straight in, or go to the nearest 24-hour "
            "emergency veterinary hospital if the clinic is closed"
        )

    return _TEMPLATE.format(
        clinic_name=settings.clinic_name,
        user_description=_user_description(full_name, role),
        today=moment.strftime("%A %d %B %Y"),
        timezone=CLINIC_TZ.key if hasattr(CLINIC_TZ, "key") else settings.clinic_timezone,
        contact_instruction=contact_instruction,
        emergency_instruction=emergency_instruction,
        emergency_signs="\n".join(f"- {sign}" for sign in EMERGENCY_SIGNS),
    )
