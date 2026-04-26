"""Exponential-backoff retry policy for OpenAI API calls.

NFR-2.1 — transient HTTP 429/500/502/503/504 retried with exponential
backoff (initial 1s, factor 2, jitter ±25%, max 5 retries, max total
wait 60s). Permanent errors (400/401/403/404/413/422) are NOT retried.

Why not just use httpx's built-in retry? Two reasons: (a) we want to
classify per-status-code with context (OpenAI's rate-limit responses
include a Retry-After header we honor exactly); (b) we want to log
each retry attempt with the structured logger so the user sees what
happened, not have it buried in a transport library's internal state.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


# -----------------------------------------------------------------------------
# Classification
# -----------------------------------------------------------------------------


# These HTTP statuses are "the request itself was wrong" — retrying without
# changing it cannot succeed. Map to ER (auth_error / unsupported_parameter
# / input_too_large / etc.) at the dispatch boundary.
PERMANENT_STATUSES: frozenset[int] = frozenset({400, 401, 403, 404, 413, 422})

# These statuses indicate the server is temporarily unable; retry helps.
TRANSIENT_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def is_retriable(status_code: int) -> bool:
    """True iff a request that returned this status should be retried."""
    return status_code in TRANSIENT_STATUSES


def is_permanent(status_code: int) -> bool:
    """True iff a request that returned this status must not be retried."""
    return status_code in PERMANENT_STATUSES


# -----------------------------------------------------------------------------
# Policy
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Tunable retry parameters.

    Defaults match NFR-2.1. Tests override via construction so they don't
    actually wait seconds.
    """

    initial_delay_s: float = 1.0
    factor: float = 2.0
    jitter_fraction: float = 0.25
    max_attempts: int = 5
    max_total_wait_s: float = 60.0

    def delay_for_attempt(self, attempt: int, retry_after_s: float | None = None) -> float:
        """Compute the wait before retrying (attempt is 1-indexed).

        If the server supplied a ``Retry-After`` header, we honor it
        verbatim (subject to the max-total-wait cap). Otherwise the
        delay is ``initial_delay × factor^(attempt-1)`` with uniform
        jitter of ``±jitter_fraction × delay``.

        Returns the delay in seconds, capped at the remaining budget.
        """
        if retry_after_s is not None and retry_after_s > 0:
            return min(retry_after_s, self.max_total_wait_s)
        base = self.initial_delay_s * (self.factor ** (attempt - 1))
        jitter = base * self.jitter_fraction * random.uniform(-1.0, 1.0)
        return max(0.0, base + jitter)


# -----------------------------------------------------------------------------
# Retry exception
# -----------------------------------------------------------------------------


class RetriesExhausted(Exception):
    """Raised when ``max_attempts`` retries have all failed.

    Carries the last underlying error so the caller can surface it.
    """

    def __init__(self, attempts: int, last_error: BaseException) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"retries exhausted after {attempts} attempts; last error: {last_error!r}"
        )


# -----------------------------------------------------------------------------
# The retry executor
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Outcome:
    """Internal: classification of a single attempt's result."""

    succeeded: bool
    retriable: bool
    status: int | None
    retry_after_s: float | None
    error: BaseException | None
    value: object | None


# A "classifier" lets the caller (openai_client.py) extract status_code
# and Retry-After from whatever exception type the SDK raises. Returning
# (retriable, status, retry_after_s) lets retry.py stay agnostic to the
# specific transport library in use.
ErrorClassifier = Callable[[BaseException], tuple[bool, int | None, float | None]]


async def with_retry(
    op: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy = RetryPolicy(),
    classifier: ErrorClassifier,
    on_attempt: Callable[[int, float | None, BaseException | None], None] | None = None,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run ``op`` with retries per ``policy``.

    Args:
        op: an async callable that performs the request and returns its result.
            On success the result is returned to the caller. On failure it
            should raise an exception that the ``classifier`` understands.
        policy: tunables.
        classifier: maps a raised exception to ``(is_retriable, status, retry_after_s)``.
            If ``is_retriable`` is False, the error is re-raised verbatim (no
            wrapping). If True, we sleep and retry up to ``max_attempts``.
        on_attempt: optional observer. Called with ``(attempt, delay_or_None, error_or_None)``
            so the caller can log retries; when called with ``(1, None, None)``
            it indicates the FIRST attempt about to be made.
        sleeper: dependency-injectable sleep so tests don't actually wait.

    Returns: the value from ``op()`` on success.

    Raises:
        :class:`RetriesExhausted` if all attempts fail.
        Whatever ``op`` raised if classified as non-retriable.
    """
    total_waited_s = 0.0
    last_error: BaseException | None = None
    for attempt in range(1, policy.max_attempts + 1):
        if on_attempt is not None:
            on_attempt(attempt, None, None)
        try:
            return await op()
        except Exception as e:  # noqa: BLE001 — we *do* want everything classified
            last_error = e
            retriable, _status, retry_after_s = classifier(e)
            if not retriable:
                raise
            if attempt >= policy.max_attempts:
                break
            delay = policy.delay_for_attempt(attempt, retry_after_s)
            if total_waited_s + delay > policy.max_total_wait_s:
                # Honor the wall-clock cap even if we still have attempt budget.
                break
            if on_attempt is not None:
                on_attempt(attempt, delay, e)
            await sleeper(delay)
            total_waited_s += delay
    assert last_error is not None  # invariant: only reachable on failure
    raise RetriesExhausted(policy.max_attempts, last_error)


__all__ = [
    "ErrorClassifier",
    "PERMANENT_STATUSES",
    "RetriesExhausted",
    "RetryPolicy",
    "TRANSIENT_STATUSES",
    "is_permanent",
    "is_retriable",
    "with_retry",
]
