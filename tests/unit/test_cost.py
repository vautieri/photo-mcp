"""Cost estimation + session-ledger tests.

FR-7.1..7.4. Verifies the price-table reader, per-call estimator,
ceiling enforcement (refuse-before-call semantics), and the running-total
math.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from photo_mcp import cost
from photo_mcp.models import ModelId


# -----------------------------------------------------------------------------
# PriceTable construction
# -----------------------------------------------------------------------------


def test_load_default_returns_table() -> None:
    table = cost.load_default()
    assert table.schema_version == "0.1.0"
    # All four supported models must have entries.
    assert set(table.by_model) >= {
        "gpt-image-1",
        "gpt-image-1-mini",
        "gpt-image-1.5",
        "gpt-image-2",
    }


def test_load_from_path_reads_user_supplied_table(tmp_path: Path) -> None:
    custom = {
        "schema_version": "0.1.0",
        "models": {
            "gpt-image-2": {
                "high_quality": {"1024x1024": 0.5},
            }
        },
    }
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(custom), encoding="utf-8")
    table = cost.load_from_path(path)
    assert table.estimate_per_image("gpt-image-2", "high", "1024x1024") == 0.5


def test_load_from_path_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(cost.PricingError):
        cost.load_from_path(tmp_path / "nope.json")


def test_load_from_path_invalid_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{ not valid", encoding="utf-8")
    with pytest.raises(cost.PricingError):
        cost.load_from_path(p)


def test_load_from_path_missing_schema_version_raises(tmp_path: Path) -> None:
    p = tmp_path / "no-schema.json"
    p.write_text(json.dumps({"models": {}}), encoding="utf-8")
    with pytest.raises(cost.PricingError):
        cost.load_from_path(p)


# -----------------------------------------------------------------------------
# estimate_per_image
# -----------------------------------------------------------------------------


def test_estimate_per_image_known_combo() -> None:
    table = cost.load_default()
    val = table.estimate_per_image("gpt-image-2", "high", "1024x1024")
    assert val > 0


def test_estimate_per_image_auto_size_returns_zero() -> None:
    table = cost.load_default()
    assert table.estimate_per_image("gpt-image-2", "high", "auto") == 0.0


def test_estimate_per_image_unknown_model_raises() -> None:
    table = cost.load_default()
    with pytest.raises(cost.PricingError):
        table.estimate_per_image("dall-e-3", "high", "1024x1024")  # type: ignore[arg-type]


def test_estimate_per_image_unknown_size_raises() -> None:
    table = cost.load_default()
    with pytest.raises(cost.PricingError):
        table.estimate_per_image("gpt-image-1", "high", "9999x9999")


def test_quality_auto_resolves_to_medium() -> None:
    """Ensures 'auto' quality estimates use the medium price tier rather than
    silently falling back to 0 or raising. The estimator can't know what the
    API will pick; medium is the documented best guess."""
    table = cost.load_default()
    medium = table.estimate_per_image("gpt-image-2", "medium", "1024x1024")
    auto   = table.estimate_per_image("gpt-image-2", "auto",   "1024x1024")
    assert auto == medium


# -----------------------------------------------------------------------------
# estimate_call
# -----------------------------------------------------------------------------


def test_estimate_call_multiplies_by_n() -> None:
    table = cost.load_default()
    e = cost.estimate_call(table=table, model="gpt-image-2", quality="high", size="1024x1024", n=4)
    assert e.n == 4
    assert e.total_usd == pytest.approx(e.per_image_usd * 4)


def test_estimate_call_n_zero_raises() -> None:
    table = cost.load_default()
    with pytest.raises(ValueError):
        cost.estimate_call(table=table, model="gpt-image-2", quality="high", size="1024x1024", n=0)


def test_estimate_call_auto_size_marks_unknown() -> None:
    table = cost.load_default()
    e = cost.estimate_call(table=table, model="gpt-image-2", quality="high", size="auto")
    assert e.is_known is False
    assert e.total_usd == 0.0


def test_estimate_call_known_size_marks_known() -> None:
    table = cost.load_default()
    e = cost.estimate_call(
        table=table, model="gpt-image-2", quality="high", size="1024x1024"
    )
    assert e.is_known is True
    assert e.total_usd > 0.0


# -----------------------------------------------------------------------------
# SessionLedger
# -----------------------------------------------------------------------------


def test_ledger_no_ceiling_authorizes_anything() -> None:
    ledger = cost.SessionLedger(ceiling_usd=0.0)  # 0 == no ceiling
    ledger.authorize_or_raise(99999.0)            # must not raise


def test_ledger_authorizes_under_ceiling() -> None:
    ledger = cost.SessionLedger(ceiling_usd=10.0)
    ledger.authorize_or_raise(5.0)                # ok
    ledger.record_billed(5.0)
    ledger.authorize_or_raise(4.99)               # still under ceiling
    assert ledger.total_usd == pytest.approx(5.0)


def test_ledger_refuses_when_call_would_exceed() -> None:
    ledger = cost.SessionLedger(ceiling_usd=10.0)
    ledger.record_billed(8.0)
    with pytest.raises(cost.CeilingExceeded) as excinfo:
        ledger.authorize_or_raise(3.0)
    err = excinfo.value
    assert err.session_total_usd == pytest.approx(8.0)
    assert err.ceiling_usd == pytest.approx(10.0)
    assert err.would_have_added_usd == pytest.approx(3.0)


def test_ledger_authorize_does_not_increment_total() -> None:
    ledger = cost.SessionLedger(ceiling_usd=10.0)
    ledger.authorize_or_raise(5.0)
    # Without record_billed, the running total stays at zero.
    assert ledger.total_usd == 0.0


def test_ledger_thread_safe() -> None:
    """Sanity check: hammer the ledger from many threads, expect total to match."""
    ledger = cost.SessionLedger(ceiling_usd=0.0)
    threads_count = 8
    increments_per_thread = 1000
    increment = 0.001

    def worker() -> None:
        for _ in range(increments_per_thread):
            ledger.record_billed(increment)

    workers = [threading.Thread(target=worker) for _ in range(threads_count)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()
    expected = threads_count * increments_per_thread * increment
    assert ledger.total_usd == pytest.approx(expected, rel=1e-6)


def test_ledger_reset_zeroes_total() -> None:
    ledger = cost.SessionLedger(ceiling_usd=10.0)
    ledger.record_billed(5.0)
    ledger.reset()
    assert ledger.total_usd == 0.0


def test_ceiling_exceeded_message_is_informative() -> None:
    err = cost.CeilingExceeded(
        session_total_usd=8.5, ceiling_usd=10.0, would_have_added_usd=2.5
    )
    msg = str(err)
    assert "8.5" in msg or "8.5000" in msg
    assert "10" in msg
    assert "2.5" in msg or "2.5000" in msg
