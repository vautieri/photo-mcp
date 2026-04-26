"""Retry policy + with_retry runner tests.

NFR-2.1, 2.2: transient errors (429/500/502/503/504) retried with
exponential backoff + jitter; permanent errors (400/401/403/404/413/422)
are NOT retried.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from photo_mcp import retry


# -----------------------------------------------------------------------------
# Classification
# -----------------------------------------------------------------------------


def test_transient_statuses_are_retriable() -> None:
    for code in (429, 500, 502, 503, 504):
        assert retry.is_retriable(code), f"{code} should be retriable"
    for code in (200, 201, 400, 401, 403, 404, 413, 418, 422):
        assert not retry.is_retriable(code), f"{code} should NOT be retriable"


def test_permanent_statuses_are_marked_permanent() -> None:
    for code in (400, 401, 403, 404, 413, 422):
        assert retry.is_permanent(code)
    for code in (200, 429, 500, 502, 503, 504):
        assert not retry.is_permanent(code)


# -----------------------------------------------------------------------------
# RetryPolicy delay math
# -----------------------------------------------------------------------------


def test_delay_grows_exponentially() -> None:
    pol = retry.RetryPolicy(initial_delay_s=1.0, factor=2.0, jitter_fraction=0.0)
    # Without jitter the math is exact: 1s, 2s, 4s, 8s, 16s.
    assert pol.delay_for_attempt(1) == pytest.approx(1.0)
    assert pol.delay_for_attempt(2) == pytest.approx(2.0)
    assert pol.delay_for_attempt(3) == pytest.approx(4.0)
    assert pol.delay_for_attempt(4) == pytest.approx(8.0)


def test_delay_jitter_within_band() -> None:
    pol = retry.RetryPolicy(initial_delay_s=10.0, factor=2.0, jitter_fraction=0.25)
    # 100 samples; each must be within ±25% of the base.
    for attempt in (1, 2, 3):
        base = pol.initial_delay_s * (pol.factor ** (attempt - 1))
        for _ in range(100):
            d = pol.delay_for_attempt(attempt)
            assert 0.75 * base - 1e-9 <= d <= 1.25 * base + 1e-9


def test_retry_after_header_overrides_backoff() -> None:
    pol = retry.RetryPolicy(initial_delay_s=1.0, factor=2.0, jitter_fraction=0.0)
    # When server provides Retry-After we honor it (within max_total_wait).
    assert pol.delay_for_attempt(1, retry_after_s=12.5) == 12.5


def test_retry_after_capped_at_max_total_wait() -> None:
    pol = retry.RetryPolicy(max_total_wait_s=30.0)
    assert pol.delay_for_attempt(1, retry_after_s=10_000.0) == 30.0


# -----------------------------------------------------------------------------
# with_retry — happy path
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_returns_value_on_success() -> None:
    async def op() -> int:
        return 42

    def classifier(_e: BaseException) -> tuple[bool, int | None, float | None]:
        return (False, None, None)

    result = await retry.with_retry(op, classifier=classifier)
    assert result == 42


@pytest.mark.asyncio
async def test_with_retry_calls_op_once_on_success() -> None:
    calls = 0

    async def op() -> int:
        nonlocal calls
        calls += 1
        return 1

    await retry.with_retry(op, classifier=lambda _e: (False, None, None))
    assert calls == 1


# -----------------------------------------------------------------------------
# with_retry — retry path
# -----------------------------------------------------------------------------


def _make_op(failures_before_success: int) -> Callable[[], Awaitable[int]]:
    """Helper: returns an op that raises N times then succeeds."""
    state = {"calls": 0}

    async def op() -> int:
        state["calls"] += 1
        if state["calls"] <= failures_before_success:
            raise RuntimeError(f"transient #{state['calls']}")
        return 42

    op._state = state  # type: ignore[attr-defined]
    return op


@pytest.mark.asyncio
async def test_with_retry_retries_until_success() -> None:
    op = _make_op(failures_before_success=2)
    sleeps: list[float] = []

    async def fake_sleep(d: float) -> None:
        sleeps.append(d)

    result = await retry.with_retry(
        op,
        policy=retry.RetryPolicy(initial_delay_s=0.001, factor=2.0, jitter_fraction=0.0),
        classifier=lambda _e: (True, 503, None),
        sleeper=fake_sleep,
    )
    assert result == 42
    assert op._state["calls"] == 3        # type: ignore[attr-defined]
    assert len(sleeps) == 2               # 2 retries → 2 sleeps


@pytest.mark.asyncio
async def test_with_retry_gives_up_after_max_attempts() -> None:
    op = _make_op(failures_before_success=999)

    async def no_sleep(_d: float) -> None:
        pass

    with pytest.raises(retry.RetriesExhausted) as excinfo:
        await retry.with_retry(
            op,
            policy=retry.RetryPolicy(initial_delay_s=0.001, max_attempts=3),
            classifier=lambda _e: (True, 503, None),
            sleeper=no_sleep,
        )
    assert excinfo.value.attempts == 3
    assert isinstance(excinfo.value.last_error, RuntimeError)


# -----------------------------------------------------------------------------
# with_retry — permanent path
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_does_not_retry_permanent_errors() -> None:
    calls = 0

    async def op() -> int:
        nonlocal calls
        calls += 1
        raise RuntimeError("400 invalid_request")

    with pytest.raises(RuntimeError):
        await retry.with_retry(
            op,
            classifier=lambda _e: (False, 400, None),
        )
    assert calls == 1


# -----------------------------------------------------------------------------
# with_retry — wall-clock cap
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_respects_total_wait_cap() -> None:
    op = _make_op(failures_before_success=999)
    waited = 0.0

    async def sleeper(d: float) -> None:
        nonlocal waited
        waited += d

    pol = retry.RetryPolicy(
        initial_delay_s=10.0,
        factor=2.0,
        jitter_fraction=0.0,
        max_attempts=10,
        max_total_wait_s=15.0,
    )
    with pytest.raises(retry.RetriesExhausted):
        await retry.with_retry(
            op,
            policy=pol,
            classifier=lambda _e: (True, 503, None),
            sleeper=sleeper,
        )
    # The cap is on the BUDGET, not the total time we slept; we should NOT
    # have slept more than max_total_wait_s.
    assert waited <= pol.max_total_wait_s


# -----------------------------------------------------------------------------
# on_attempt observer
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_invokes_observer() -> None:
    op = _make_op(failures_before_success=1)
    seen: list[tuple[int, float | None, str | None]] = []

    def observer(attempt: int, delay: float | None, err: BaseException | None) -> None:
        seen.append((attempt, delay, type(err).__name__ if err else None))

    await retry.with_retry(
        op,
        policy=retry.RetryPolicy(initial_delay_s=0.001),
        classifier=lambda _e: (True, 500, None),
        sleeper=lambda _d: asyncio.sleep(0),
        on_attempt=observer,
    )
    # Observer is called once per attempt (attempt-start), and again
    # before each sleep. We expect at least: (1, None, None), (1, delay, error), (2, None, None)
    attempts_started = [s for s in seen if s[1] is None and s[2] is None]
    assert len(attempts_started) == 2
