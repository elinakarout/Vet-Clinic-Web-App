"""The streaming model client used by the /chat router. (Phase 7)

Speaks the OpenAI-compatible ``POST /chat/completions`` that **both** Google AI
Studio and OpenRouter serve, so ``settings.chat_base_url`` decides the gateway
and no code changes when it moves. PROJECT_PLAN.md sec 7 assumed the ``anthropic``
SDK and its tool runner; neither is installed here, so the wire format is handled
directly on top of ``httpx`` -- already a dependency since Phase 0. See
PHASE_7.md decisions 1 and 2.

**Synchronous on purpose.** Everything else in this codebase uses sync
SQLAlchemy, and the tool calls in agent.py do real database work. An ``async``
route would either block the event loop on every tool call or need
``anyio.to_thread`` wrapped around all of it. FastAPI runs a ``def`` route in a
threadpool and Starlette iterates a sync generator the same way, so
``StreamingResponse`` works and the Session never leaves its thread.

Three things about the wire format that a plausible-looking rewrite breaks:

* **Tool-call arguments arrive in fragments, keyed by index.** One call's
  ``{"pet_id": 3}`` can come as ``{"pet_``, ``id": ``, ``3}`` across three
  deltas, and two parallel calls interleave. They are merged on
  ``tool_calls[i].index``, never on arrival order. Google usually sends arguments
  whole and OpenRouter usually fragments them, so a client tested against only
  one of the two looks fine and fails on the other.
* **``content`` is frequently ``null``**, not absent and not ``""``.
* **An error is a JSON body, not an SSE frame.** A 200 that starts streaming and
  a 429 that returns ``{"error": ...}`` need different handling, and the second
  must not be parsed as an empty stream -- that would look like a model that
  simply had nothing to say.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ChatClientError(Exception):
    """Base for everything this module refuses to do or cannot finish."""


class ChatConfigError(ChatClientError):
    """No API key configured. A deployment mistake, not a user's fault."""


class ChatRateLimited(ChatClientError):
    """The provider said 429. Worth distinguishing: the user should just retry."""


class ChatUnavailable(ChatClientError):
    """The provider failed, timed out, or returned something unusable."""


@dataclass
class ToolCall:
    """One accumulated tool call. ``arguments`` is raw JSON text, not a dict.

    ``extra_content`` is an opaque provider passthrough. Gemini 3 puts a
    ``google.thought_signature`` there and **rejects the follow-up request with
    a 400 if it is not echoed back** on the assistant turn, so this is carried
    without being interpreted. Gateways that send nothing leave it ``None`` and
    the key is omitted -- see ``agent._assistant_message``.
    """

    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""
    extra_content: dict[str, Any] | None = None


@dataclass
class Completion:
    """What one streamed model turn produced."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None


# ---------------------------------------------------------------------------
# The HTTP client
# ---------------------------------------------------------------------------

_client: httpx.Client | None = None


def get_client() -> httpx.Client:
    """The shared httpx.Client, created on first use.

    Lazy and memoised for the same reason rag/store.py's collection is:
    tests/conftest.py imports app.main, and a connection pool built at import
    would be created by every test in the suite whether or not it chats.
    """
    global _client
    if _client is None:
        _client = httpx.Client(timeout=settings.chat_request_timeout_seconds)
    return _client


def set_client(client: httpx.Client | None) -> None:
    """Swap the client, or reset it with None. Tests inject httpx.MockTransport here."""
    global _client
    if _client is not None and client is not _client:
        try:
            _client.close()
        except Exception:  # pragma: no cover - closing a dead client is not interesting
            pass
    _client = client


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def _merge_tool_call_deltas(
    accumulator: dict[int, ToolCall], deltas: list[dict[str, Any]]
) -> None:
    """Fold one delta's ``tool_calls`` into the accumulator, keyed by index.

    The index is the identity of a call within the turn; ``id`` and ``name``
    arrive once, ``arguments`` arrive in pieces and are concatenated. Keying on
    anything else -- arrival order, or the name once it is known -- corrupts two
    parallel calls into one.

    **Google AI Studio omits `index` entirely, even with several calls in
    flight** (measured during Phase 7 verification), sending each parallel call
    in its own frame. Defaulting a missing index to 0 therefore collapsed two
    calls into one: the second name overwrote the first and their argument
    strings concatenated into invalid JSON (``{}{"query":"..."}``). So when the
    index is absent, fall back to the OpenAI-spec rule that marks call
    boundaries -- a delta carrying a ``name`` or an ``id`` *starts* a call, one
    carrying only ``arguments`` *continues* the newest -- which keeps fragmented
    arguments working on gateways that omit the index as well.
    """
    for delta in deltas:
        raw_index = delta.get("index")
        if raw_index is None:
            function_part = delta.get("function") or {}
            starts_new_call = bool(function_part.get("name") or delta.get("id"))
            if not accumulator:
                index = 0
            elif starts_new_call:
                index = max(accumulator) + 1
            else:
                index = max(accumulator)
        else:
            index = int(raw_index)
        call = accumulator.setdefault(index, ToolCall(index=index))
        if delta.get("id"):
            call.id = delta["id"]
        function = delta.get("function") or {}
        if function.get("name"):
            call.name = function["name"]
        arguments = function.get("arguments")
        if arguments:
            call.arguments += arguments
        if delta.get("extra_content"):
            call.extra_content = delta["extra_content"]


def _build_payload(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.chat_model,
        "messages": messages,
        "stream": True,
        "max_tokens": settings.chat_max_tokens,
        "temperature": settings.chat_temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if settings.chat_reasoning_effort:
        # Omitted entirely when unset: a gateway that does not know the field
        # answers 400 rather than ignoring it.
        payload["reasoning_effort"] = settings.chat_reasoning_effort
    return payload


def _raise_for_error_body(response: httpx.Response) -> None:
    """Turn a non-200 into the right exception, with the provider's own words."""
    try:
        body = response.read().decode("utf-8", "replace")
    except Exception:  # pragma: no cover - body already consumed
        body = ""
    detail = body[:400]
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
            detail = str(parsed["error"].get("message") or detail)
    except (json.JSONDecodeError, TypeError):
        pass

    logger.warning("Chat provider returned %s: %s", response.status_code, detail)
    if response.status_code == 429:
        raise ChatRateLimited(detail or "The assistant is rate limited right now.")
    raise ChatUnavailable(detail or f"The assistant returned HTTP {response.status_code}.")


def stream_completion(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> Iterator[tuple[str, Any]]:
    """Stream one model turn.

    Yields ``("text", chunk)`` as prose arrives, then exactly one
    ``("done", Completion)`` at the end. The Completion carries the full text and
    any accumulated tool calls, so the caller does not have to re-assemble what it
    already streamed.

    Raises ChatConfigError / ChatRateLimited / ChatUnavailable. Callers must
    handle those *before* the first byte reaches the browser where they can --
    see routers/chat.py.
    """
    api_key = settings.chat_api_key
    if not api_key:
        raise ChatConfigError(
            "No chat API key is configured. Set GOOGLE_AI_STUDIO_API_KEY (or "
            "OPENROUTER_API_KEY) in api/.env."
        )

    url = settings.chat_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    text_parts: list[str] = []
    tool_calls: dict[int, ToolCall] = {}
    finish_reason: str | None = None

    try:
        with get_client().stream(
            "POST", url, headers=headers, json=_build_payload(messages, tools)
        ) as response:
            if response.status_code != 200:
                _raise_for_error_body(response)

            for line in response.iter_lines():
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    # Comments (": keep-alive"), `event:` lines and blank framing.
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    # A truncated frame is not worth killing a live reply over.
                    logger.debug("Skipping unparseable SSE frame: %r", data[:120])
                    continue

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

                delta = choice.get("delta") or {}
                content = delta.get("content")
                if content:
                    # `is not None` would be wrong as well as redundant: an empty
                    # string is a no-op, and `content` is very often null.
                    text_parts.append(content)
                    yield ("text", content)

                if delta.get("tool_calls"):
                    _merge_tool_call_deltas(tool_calls, delta["tool_calls"])

    except ChatClientError:
        raise
    except httpx.TimeoutException as exc:
        raise ChatUnavailable("The assistant took too long to respond.") from exc
    except httpx.HTTPError as exc:
        logger.exception("Chat provider request failed")
        raise ChatUnavailable("Could not reach the assistant.") from exc

    yield (
        "done",
        Completion(
            text="".join(text_parts),
            tool_calls=[tool_calls[i] for i in sorted(tool_calls)],
            finish_reason=finish_reason,
        ),
    )
