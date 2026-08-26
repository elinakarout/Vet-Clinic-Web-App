"""POST /chat -- streaming chatbot endpoint, plus conversation history. (Phase 7)

HTTP only (CLAUDE.md's layering rule). The tool loop lives in app/chat/agent.py
and every rule about what the assistant may do lives in app/chat/tools.py; this
file turns a request into a call and a stream of event dicts into SSE frames.

**Everything that can fail is made to fail before the first byte.** An empty
message, a conversation that is not yours, a missing API key, the rate limit --
all raised while the response status is still negotiable, so they come back as a
real 401/403/404/422/429/503. Once a StreamingResponse has started, the status
line is already 200 and the only way left to report a problem is an `error`
event, which the browser has to be written to notice. The narrow window that
genuinely cannot be hoisted -- the provider dying mid-reply -- is exactly what
that event is for.

The route is `def`, not `async def`. See app/chat/client.py for why.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat import client as model_client
from app.chat.agent import run_chat
from app.config import settings
from app.database import get_db
from app.deps import get_current_user, get_owned_conversation
from app.models import ChatMessage, ChatRole, Conversation, User
from app.schemas.chat import (
    ChatRequest,
    ConversationDetailOut,
    ConversationOut,
)
from app.services.ratelimit import SlidingWindow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_UNPROCESSABLE = 422  # see routers/appointments.py for why this is a bare int


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
#
# Phase 9 moved the window itself into services/ratelimit.py, where
# /auth/login now shares it, and that module documents what this does and does
# not protect. It is still process-local: it resets on restart and each uvicorn
# worker keeps its own count. It exists because /chat spends money and free-tier
# quota per call, and a render loop in the frontend can burn a day's allowance
# before anyone notices.

_hits = SlidingWindow()


def _rate_limit(current_user: User = Depends(get_current_user)) -> User:
    limit = settings.chat_rate_limit_per_minute
    retry_after = _hits.is_blocked(current_user.id, limit)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many messages. Please wait a moment -- the assistant accepts "
            f"{limit} messages a minute.",
            headers={"Retry-After": str(retry_after)},
        )
    _hits.record(current_user.id)
    return current_user


def reset_rate_limits() -> None:
    """Clear the window. For tests, and for a deliberate reset in a REPL."""
    _hits.clear()


# ---------------------------------------------------------------------------
# The stream
# ---------------------------------------------------------------------------


def _sse(event: dict) -> str:
    """One SSE frame. `ensure_ascii` off so an accented pet name survives intact."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _title_from(message: str) -> str:
    """A short label for the conversation list, taken from the opening line."""
    flat = " ".join(message.split())
    return flat[:80] if len(flat) <= 80 else flat[:77] + "..."


@router.post("")
def chat(
    payload: ChatRequest,
    current_user: User = Depends(_rate_limit),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Send one message and stream the assistant's reply back.

    Returns `text/event-stream`, one JSON object per `data:` line. See API.md for
    the event shapes; `done` carries the ids the client needs to keep talking.

    Any authenticated user may chat. The tools that need a client profile answer
    staff with a plain sentence rather than an error -- PHASE_7.md decision 5.
    """
    message = payload.message.strip()
    if not message:
        raise HTTPException(_UNPROCESSABLE, "Message cannot be blank")

    if not settings.chat_api_key:
        # A deployment mistake, not the caller's. Reported here so it is a clean
        # 503 rather than an `error` event inside a 200 nobody reads.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The assistant is not configured. Please contact the clinic.",
        )

    if payload.conversation_id is None:
        conversation = Conversation(user_id=current_user.id, title=_title_from(message))
        db.add(conversation)
        db.flush()
    else:
        # The same ownership check GET /chat/conversations/{id} uses, called
        # directly because the id arrives in the body rather than the path --
        # exactly how routers/appointments.py reuses get_owned_pet.
        conversation = get_owned_conversation(
            conversation_id=payload.conversation_id, current_user=current_user, db=db
        )
        if conversation.title is None:
            conversation.title = _title_from(message)

    db.add(
        ChatMessage(
            conversation_id=conversation.id, role=ChatRole.USER, content=message
        )
    )
    db.commit()
    db.refresh(conversation)

    def event_stream() -> Iterator[str]:
        try:
            for event in run_chat(
                db=db,
                current_user=current_user,
                conversation=conversation,
                user_message=message,
            ):
                yield _sse(event)
        except model_client.ChatRateLimited as exc:
            yield _sse({"type": "error", "detail": str(exc)})
        except model_client.ChatClientError as exc:
            yield _sse({"type": "error", "detail": str(exc)})
        except Exception:
            # The reply is already half on screen; a traceback would reach the
            # browser as a broken stream. PROJECT_PLAN.md section 8: no stack traces
            # in responses.
            logger.exception("Chat turn failed for user %s", current_user.id)
            db.rollback()
            yield _sse(
                {
                    "type": "error",
                    "detail": "Something went wrong. Please try again, or call the clinic.",
                }
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # nginx buffers proxied responses by default, which holds a streamed
            # reply until it finishes -- turning token-by-token into all-at-once
            # with no error to explain it. Ignored by every other server.
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConversationOut]:
    """The caller's own threads, most recently used first.

    Scoped in the WHERE clause rather than filtered afterwards, and there is no
    `user_id` parameter to widen it with -- the same rule pets_visible_to and
    appointments_visible_to apply.
    """
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [ConversationOut.model_validate(row) for row in db.scalars(stmt)]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def read_conversation(
    conversation: Conversation = Depends(get_owned_conversation),
) -> ConversationDetailOut:
    """One thread with its transcript, oldest first.

    This is what makes a refresh non-destructive: the assistant rows carry the
    proposals they produced, so Phase 8 re-renders the slot cards without asking
    the model anything again.
    """
    return ConversationDetailOut.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation: Conversation = Depends(get_owned_conversation),
    db: Session = Depends(get_db),
) -> None:
    """Delete a thread and its messages.

    A real delete, unlike a pet: `pets.py:pet_has_history` refuses because a
    clinic may not lose a vaccination record, whereas a chat transcript is the
    user's own and deleting it is the point. The cascade on Conversation.messages
    takes the rows with it.
    """
    db.delete(conversation)
    db.commit()
