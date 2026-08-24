"""SQLAlchemy models: conversations, chat_messages. (Phase 7)

PROJECT_PLAN.md Phase 7 step 5 asks for conversation history "per user so
context survives page reloads". These two tables are that, and the shape of them
encodes one decision worth stating up front.

**Only USER and ASSISTANT turns are stored.** A turn where the model called
``find_available_slots`` and got back a list of openings is *not* persisted, even
though replaying it would make a resumed conversation byte-identical for the
model. Availability goes stale: an hour later those slots may be booked, and
feeding them back as though they were current is how the chatbot ends up
confidently offering a time that no longer exists. Dropping tool turns makes that
impossible rather than merely unlikely, and the model simply calls the tool again
with fresh data. See PHASE_7.md decision 3.

``ChatMessage.payload`` is the compensation for that: an assistant row carries
the proposals it produced, so Phase 8 can re-render the slot cards after a reload
without re-running the model.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ChatRole(str, enum.Enum):
    """Who said it.

    Deliberately two values, not four. There is no SYSTEM because the prompt is
    rebuilt every request (it embeds today's date), and no TOOL because tool
    turns are not persisted -- see the module docstring.
    """

    USER = "USER"
    ASSISTANT = "ASSISTANT"


class Conversation(Base):
    """One chat thread, owned by one user.

    Scoped to ``users.id`` rather than ``client_profiles.id``, unlike pets: a
    conversation belongs to whoever logged in, and PHASE_7.md's access decision
    lets staff use the assistant too. This is the one place in the codebase where
    ``user_id`` really is the right foreign key.
    """

    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Derived from the opening message so a sidebar has something to show. Null
    # until the first user turn lands.
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Touched on every turn, so "most recent conversation" is one ORDER BY.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChatMessage.id",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Conversation id={self.id} user_id={self.user_id} title={self.title!r}>"


class ChatMessage(Base):
    """One turn. Ordered by id -- created_at has second resolution at best."""

    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_conversation_id", "conversation_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[ChatRole] = mapped_column(
        SAEnum(ChatRole, name="chat_role", native_enum=False, length=16, validate_strings=True),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # {"proposals": [...], "tools_used": [...]} on assistant rows, null on user
    # rows. Plain JSON rather than JSONB: this has to work on SQLite in dev and
    # PostgreSQL in production off the same model, and nothing queries into it.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ChatMessage id={self.id} conversation_id={self.conversation_id} role={self.role}>"
