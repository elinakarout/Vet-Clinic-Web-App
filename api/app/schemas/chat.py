"""Pydantic schemas for /chat: the request, the two proposals, and history. (Phase 7)

Two rules from elsewhere in the codebase land here.

**Never return a SQLAlchemy model** (root CLAUDE.md): ``ChatMessageOut`` exists so
a transcript can be read back without ``Conversation.user`` trailing a
``hashed_password`` behind it.

**The client never constructs a `starts_at`** (FRONTEND.md): ``starts_at`` on
``AppointmentProposal`` is the exact ``scheduling.Slot.starts_at`` the engine
produced, serialised aware-UTC. Phase 8 passes that value straight to
``POST /appointments``, where AppointmentCreate requires both an explicit offset
and an exact slot boundary. Rounding it, re-parsing it in browser time, or
rebuilding it from the human-readable label would break one or both.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models import ChatRole
from app.services.timeutils import ensure_utc


class _UtcModel(BaseModel):
    """Serialises every datetime field as aware UTC.

    The same shim as schemas/appointment.py:_UtcModel, and for the same reason:
    SQLite hands back naive datetimes even from a DateTime(timezone=True) column,
    and a proposal that serialised as "2026-09-01T09:00:00" would be re-read by
    the browser in browser-local time. Duplicated rather than imported so the
    appointment schemas keep no dependency on the chat ones.
    """

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("starts_at", "ends_at", "created_at", "updated_at", check_fields=False)
    def _serialise_utc(self, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """One user turn.

    ``extra="forbid"`` for the reason PHASE_2.md gives for ClientRegister: a
    request body is the attacker's half of the conversation, and a smuggled
    ``"role"``, ``"system"`` or ``"user_id"`` key must be a 422 rather than
    something a later refactor might start honouring.

    Omitting ``conversation_id`` starts a new thread. There is no field for the
    prior messages -- history comes from the database, keyed on the JWT's user,
    so a caller cannot forge what they said earlier.
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = Field(default=None, gt=0)


# ---------------------------------------------------------------------------
# Proposals -- structured data the UI renders as a Confirm card
# ---------------------------------------------------------------------------


class AppointmentProposal(_UtcModel):
    """A booking the model is suggesting. **Nothing has been written.**

    The names are carried alongside the ids because AppointmentOut has neither,
    and a card reading "Book Rex with Dr. Haddad" should not need two more round
    trips to render. Clicking it calls POST /appointments with pet_id, vet_id,
    starts_at and reason -- the same code path as manual booking.
    """

    pet_id: int
    pet_name: str
    vet_id: int
    vet_name: str
    starts_at: datetime
    ends_at: datetime
    reason: str | None = None


class CancellationProposal(_UtcModel):
    """A cancellation the model is suggesting. **Nothing has been written.**

    PROJECT_PLAN.md sec 7's tool table had the chatbot cancel outright. It proposes
    instead, for the reason the same document gives for booking: if the model
    misunderstands, the worst case should be a card the user declines, not a
    consultation silently removed from a vet's calendar. Clicking it calls the
    ordinary POST /appointments/{id}/cancel. See PHASE_7.md decision 6.
    """

    appointment_id: int
    pet_id: int
    pet_name: str
    vet_name: str
    starts_at: datetime
    ends_at: datetime
    reason: str | None = None


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class ChatMessageOut(_UtcModel):
    """One stored turn, as the API describes it."""

    id: int
    role: ChatRole
    content: str
    # {"proposals": [...], "tools_used": [...]} on assistant rows. Phase 8 reads
    # it to re-render slot cards after a reload without re-running the model.
    payload: dict[str, Any] | None = None
    created_at: datetime


class ConversationOut(_UtcModel):
    """A thread in the list. No messages -- that is the detail view's job."""

    id: int
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    """A thread with its transcript, oldest first."""

    messages: list[ChatMessageOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# The event stream (documented here, emitted by routers/chat.py)
# ---------------------------------------------------------------------------
#
# POST /chat streams `text/event-stream`, one JSON object per `data:` line.
# These models are not used to parse anything -- they exist so the contract Phase
# 8 codes against is written down in one place and stays in step with API.md.


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    text: str


class ToolStartEvent(BaseModel):
    type: Literal["tool_start"] = "tool_start"
    name: str
    # Human-readable, e.g. "Checking availability...". Sent by the server so
    # PROJECT_PLAN.md Phase 8 step 3 needs no name->label table in the client.
    label: str


class ToolEndEvent(BaseModel):
    type: Literal["tool_end"] = "tool_end"
    name: str


class ProposalEvent(BaseModel):
    type: Literal["proposal"] = "proposal"
    kind: Literal["appointment", "cancellation"]
    proposal: dict[str, Any]


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    conversation_id: int
    message_id: int


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    detail: str
