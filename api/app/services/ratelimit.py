"""A sliding-window counter, shared by the endpoints that need throttling. (Phase 9)

Phase 7 grew a rate limiter inside routers/chat.py because /chat spends free-tier
quota per call. Phase 9's QA pass found /auth/login had none at all -- fifteen
consecutive wrong passwords all answered 401 -- so rather than write the same
deque-in-a-dict a second time, that logic moved here and both callers use it.

The honest limits of this implementation, unchanged from Phase 7's note:

- It lives in a process-local dict, so it resets on restart and each uvicorn
  worker keeps its own count. With four workers the real ceiling is four times
  the configured number. That is still worth having -- it turns an unbounded
  guessing loop into a slow one -- but it is not a substitute for a shared store
  (Redis) or an edge rate limiter once this is on the internet.
- Keys are caller-supplied. `client.host` is the *proxy's* address behind a load
  balancer, so a deployment must either trust a forwarded header explicitly or
  accept that the whole fleet shares one bucket.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindow:
    """Counts hits per key over a rolling window.

    Deliberately not a decorator or a middleware: the two call sites want
    different keys (a user id for chat, an address-plus-email pair for login) and
    different moments (chat counts every request, login counts only failures).
    """

    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window = window_seconds
        self._hits: dict[object, deque[float]] = defaultdict(deque)

    def _prune(self, key: object, now: float) -> deque[float]:
        window = self._hits[key]
        while window and now - window[0] > self._window:
            window.popleft()
        return window

    def is_blocked(self, key: object, limit: int) -> int | None:
        """Seconds the caller must wait, or None if it may proceed.

        Does not record anything. `limit <= 0` disables the check, which is how
        a test or a local REPL turns throttling off through configuration alone.
        """
        if limit <= 0:
            return None
        now = time.monotonic()
        window = self._prune(key, now)
        if len(window) < limit:
            return None
        return max(1, int(self._window - (now - window[0])) + 1)

    def record(self, key: object) -> None:
        """Count one hit against `key`."""
        now = time.monotonic()
        self._prune(key, now)
        self._hits[key].append(now)

    def clear(self, key: object | None = None) -> None:
        """Forget one key, or all of them.

        Clearing a single key is what a *successful* login does: a person who
        mistypes twice and then gets it right should not carry a penalty into
        their next session.
        """
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)
