"""run_chat -- the call/execute/continue loop and the event stream. (Phase 7)

PROJECT_PLAN.md sec 7 hands this job to the anthropic SDK's tool runner ("the SDK's
tool runner handles the call-execute-continue loop for you"). There is no such
runner here, so the loop is explicit: stream a turn, and if the model asked for
tools, run them, append the results, and ask again.

Nothing in this module knows what an HTTP status code is (CLAUDE.md's layering
rule). It yields plain event dicts; routers/chat.py frames them as SSE.

**History is capped and tool turns are not persisted.** Within one call the
``messages`` list grows to hold the assistant's tool calls and their results,
because the model needs them to finish the turn. None of that is written to
``chat_messages`` -- see app/models/chat.py for why replaying stale availability
would be worse than making the model look it up again.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat import client as model_client
from app.chat.prompts import build_system_prompt
from app.chat.tools import ToolRegistry, build_tools
from app.config import settings
from app.models import ChatMessage, ChatRole, Conversation, Role, User
from app.services.timeutils import now_utc

logger = logging.getLogger(__name__)

# Shown when the model runs out of tool iterations. Not an exception: the user has
# already watched several status lines go by, and a stack trace is a worse ending
# than an apology.
_STUCK_MESSAGE = (
    "Sorry -- I got stuck working that out. Could you try asking me again, "
    "or call the clinic if it is urgent?"
)


def _display_name(user: User) -> str | None:
    if user.role is Role.CLIENT and user.client_profile is not None:
        return user.client_profile.full_name
    if user.role is Role.VET and user.vet_profile is not None:
        return user.vet_profile.full_name
    return None


def load_history(db: Session, conversation: Conversation) -> list[dict[str, Any]]:
    """The last ``chat_history_limit`` turns, oldest first, as wire messages.

    PROJECT_PLAN.md sec 7 "Cost and latency": cap the history so long chats do not
    grow unboundedly. Selected newest-first with a LIMIT and then reversed, so a
    thousand-message conversation reads twenty rows rather than all of them.
    """
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.id.desc())
            .limit(settings.chat_history_limit)
        )
    )
    rows.reverse()
    return [
        {
            "role": "user" if row.role is ChatRole.USER else "assistant",
            "content": row.content,
        }
        for row in rows
    ]


def _assistant_message(completion: model_client.Completion) -> dict[str, Any]:
    """The assistant turn to append before the tool results.

    ``content`` must be present even when empty -- a turn that was only tool calls
    still needs the key, and some gateways reject a message object without it.
    """
    message: dict[str, Any] = {"role": "assistant", "content": completion.text or ""}
    if completion.tool_calls:
        calls: list[dict[str, Any]] = []
        for call in completion.tool_calls:
            entry: dict[str, Any] = {
                "id": call.id or f"call_{call.index}",
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments or "{}"},
            }
            # Gemini 3 answers 400 "Function call is missing a thought_signature
            # in functionCall parts" if this is not echoed back verbatim, which
            # kills every tool-using turn. It is opaque and provider-specific, so
            # it is round-tripped rather than read; gateways that send none get
            # no key. Measured in Phase 7 verification.
            if call.extra_content:
                entry["extra_content"] = call.extra_content
            calls.append(entry)
        message["tool_calls"] = calls
    return message


def run_chat(
    *,
    db: Session,
    current_user: User,
    conversation: Conversation,
    user_message: str,
) -> Iterator[dict[str, Any]]:
    """Run one user turn and yield events until it is finished.

    The caller has already persisted ``user_message`` and checked that
    ``conversation`` belongs to ``current_user``. This function owns everything
    after that, including persisting the assistant's reply.
    """
    registry: ToolRegistry = build_tools(current_user, db)

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": build_system_prompt(
                full_name=_display_name(current_user), role=current_user.role.value
            ),
        }
    ]
    messages.extend(load_history(db, conversation))

    reply_parts: list[str] = []
    completion: model_client.Completion | None = None

    for iteration in range(settings.chat_max_tool_iterations):
        completion = None
        for kind, value in model_client.stream_completion(
            messages=messages, tools=registry.schemas
        ):
            if kind == "text":
                reply_parts.append(value)
                yield {"type": "token", "text": value}
            else:
                completion = value

        if completion is None:  # pragma: no cover - stream_completion always ends with done
            break

        if not completion.tool_calls:
            break

        messages.append(_assistant_message(completion))

        for call in completion.tool_calls:
            yield {
                "type": "tool_start",
                "name": call.name,
                "label": registry.label_for(call.name),
            }
            result = registry.call(call.name, call.arguments)
            yield {"type": "tool_end", "name": call.name}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id or f"call_{call.index}",
                    "content": result,
                }
            )
    else:
        # The for-else fires only if the loop was never broken out of, i.e. the
        # model asked for tools on every single iteration and never settled.
        logger.warning(
            "Chat hit the %s-iteration tool cap for user %s",
            settings.chat_max_tool_iterations,
            current_user.id,
        )
        reply_parts.append(_STUCK_MESSAGE)
        yield {"type": "token", "text": _STUCK_MESSAGE}

    for proposal in registry.proposals:
        yield {"type": "proposal", **proposal}

    reply = "".join(reply_parts).strip()
    if not reply:
        # A turn that produced only tool calls and no prose. Rare, but it must not
        # persist an empty assistant row -- the next request would send a blank
        # message and some gateways reject that.
        reply = (
            "Sorry -- I do not have an answer for that. Please call the clinic and "
            "someone will help."
        )
        yield {"type": "token", "text": reply}

    # Null rather than an empty shell when the turn used no tools and proposed
    # nothing, so a plain question does not store two empty lists per reply.
    payload: dict[str, Any] | None = None
    if registry.proposals or registry.used:
        payload = {"proposals": registry.proposals, "tools_used": registry.used}

    stored = ChatMessage(
        conversation_id=conversation.id,
        role=ChatRole.ASSISTANT,
        content=reply,
        payload=payload,
    )
    db.add(stored)
    conversation.updated_at = now_utc()
    db.commit()
    db.refresh(stored)

    yield {"type": "done", "conversation_id": conversation.id, "message_id": stored.id}
