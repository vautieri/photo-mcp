"""Cost estimation and per-session ceiling enforcement.

FR-7.1..7.4 — every tool result includes a USD estimate; an explicit
ceiling refuses calls that would push the running session total over.

The price table lives in :mod:`prices.json` and is read once at module
load. Updating prices is a file edit + version bump in the JSON's
``schema_version`` field; no code change required.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Final

from photo_mcp.models import ModelId, QualityLevel

_QUALITY_KEY: Final[dict[QualityLevel, str]] = {
    "low":    "low_quality",
    "medium": "medium_quality",
    "high":   "high_quality",
    "auto":   "medium_quality",  # auto resolves to medium for estimation purposes
}


# -----------------------------------------------------------------------------
# Errors
# -----------------------------------------------------------------------------


class PricingError(Exception):
    """Raised when the price table is missing or malformed."""


class CeilingExceeded(Exception):
    """Raised when a planned call would push session total past the ceiling.

    Mapped to ER-7 cost_ceiling at the dispatch boundary. The exception
    payload carries the running total, the ceiling, and the rejected
    delta so the LLM can show the user a meaningful refusal.
    """

    def __init__(
        self,
        *,
        session_total_usd: float,
        ceiling_usd: float,
        would_have_added_usd: float,
    ) -> None:
        self.session_total_usd = session_total_usd
        self.ceiling_usd = ceiling_usd
        self.would_have_added_usd = would_have_added_usd
        super().__init__(
            f"Cost ceiling reached: session total ${session_total_usd:.4f}, "
            f"this call would add ${would_have_added_usd:.4f} (ceiling "
            f"${ceiling_usd:.4f}). Raise the ceiling or split the workload."
        )


# -----------------------------------------------------------------------------
# Price table
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PriceTable:
    """In-memory representation of ``prices.json``.

    Constructed via :func:`load_default` or :func:`load_from_path`. Frozen
    so a Config-time table cannot be silently mutated by tool code.
    """

    schema_version: str
    by_model: dict[str, dict[str, dict[str, float]]]
    source_path: Path | None

    def estimate_per_image(self, model: ModelId, quality: QualityLevel, size: str) -> float:
        """Look up cost for a single image of the given (model, quality, size).

        Returns ``0.0`` if the size is ``auto`` (we can't price it
        without knowing the resolved size; caller should re-call after
        the API picks an actual size). Raises :class:`PricingError` if
        the (model, quality, size) tuple is not in the table.
        """
        if size == "auto":
            return 0.0
        per_model = self.by_model.get(model)
        if per_model is None:
            raise PricingError(f"no price entry for model {model!r}")
        per_quality = per_model.get(_QUALITY_KEY[quality])
        if per_quality is None:
            raise PricingError(
                f"no price entry for ({model!r}, quality={quality!r})"
            )
        per_size = per_quality.get(size)
        if per_size is None:
            raise PricingError(
                f"no price entry for ({model!r}, {quality!r}, size={size!r}); "
                f"prices.json may need updating"
            )
        return float(per_size)


def load_default() -> PriceTable:
    """Load the bundled prices.json shipped with the package."""
    with resources.files("photo_mcp").joinpath("prices.json").open("r", encoding="utf-8") as f:
        data = json.load(f)
    return _from_dict(data, source_path=None)


def load_from_path(path: Path) -> PriceTable:
    """Load a prices.json from an arbitrary path. Used in tests + by Config."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise PricingError(f"prices file not found: {path}") from e
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise PricingError(f"prices file at {path} is not valid JSON: {e}") from e
    return _from_dict(data, source_path=path)


def _from_dict(data: dict[str, object], *, source_path: Path | None) -> PriceTable:
    schema = data.get("schema_version")
    if not isinstance(schema, str):
        raise PricingError("prices.json missing string 'schema_version'")
    by_model_raw = data.get("models")
    if not isinstance(by_model_raw, dict):
        raise PricingError("prices.json missing 'models' object")
    # Validate shape: models -> quality -> size -> float. Cheap structural check.
    by_model: dict[str, dict[str, dict[str, float]]] = {}
    for model, qualities in by_model_raw.items():
        if not isinstance(qualities, dict):
            raise PricingError(f"prices.json[{model}] is not an object")
        per_quality: dict[str, dict[str, float]] = {}
        for q, sizes in qualities.items():
            if not isinstance(sizes, dict):
                raise PricingError(f"prices.json[{model}][{q}] is not an object")
            per_size: dict[str, float] = {}
            for sz, val in sizes.items():
                if not isinstance(val, (int, float)):
                    raise PricingError(
                        f"prices.json[{model}][{q}][{sz}] is not numeric"
                    )
                per_size[sz] = float(val)
            per_quality[q] = per_size
        by_model[model] = per_quality
    return PriceTable(schema_version=schema, by_model=by_model, source_path=source_path)


# -----------------------------------------------------------------------------
# Per-call estimator
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """Detailed estimate for a single tool call."""

    model: ModelId
    quality: QualityLevel
    size: str
    n: int
    per_image_usd: float
    total_usd: float

    @property
    def is_known(self) -> bool:
        """True when the table had a price for this (model, quality, size).

        Auto-size estimates report 0.0 and ``is_known=False`` so the
        caller can present "estimate unavailable until size resolves".
        """
        return self.per_image_usd > 0.0


def estimate_call(
    *,
    table: PriceTable,
    model: ModelId,
    quality: QualityLevel,
    size: str,
    n: int = 1,
) -> CostEstimate:
    """Compute the cost estimate for a single tool call.

    Raises :class:`PricingError` if the (model, quality, size) tuple is
    missing from the table — that's a bug, not a runtime condition. Use
    ``size="auto"`` to indicate "size will be picked by the API"; the
    estimate then reports 0.0 (caller refines after the response).
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    per = table.estimate_per_image(model, quality, size)
    return CostEstimate(
        model=model,
        quality=quality,
        size=size,
        n=n,
        per_image_usd=per,
        total_usd=per * n,
    )


# -----------------------------------------------------------------------------
# Session ledger + ceiling enforcement
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class SessionLedger:
    """Running per-session cost total + ceiling guard.

    Thread-safe: a single MCP server may serve concurrent SSE clients
    (one ledger per client) or a single stdio client (one ledger
    overall). The guard refuses the call BEFORE the API request is
    made; it does not retroactively refund.

    A ceiling of ``0.0`` means "no ceiling" — the server logs running
    totals but never refuses on cost grounds.
    """

    ceiling_usd: float = 0.0
    _total_usd: float = 0.0
    _lock: threading.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Initialize the lock outside the dataclass field default to
        # avoid sharing a single Lock across all instances.
        self._lock = threading.Lock()

    @property
    def total_usd(self) -> float:
        with self._lock:
            return self._total_usd

    def authorize_or_raise(self, planned_call_usd: float) -> None:
        """Check the planned cost against the ceiling. Raise on violation.

        Does NOT yet add the cost to the running total — call
        :meth:`record_billed` after the API responds with actual usage.
        This avoids charging the user for refused calls.
        """
        if self.ceiling_usd <= 0.0:
            return  # no ceiling
        with self._lock:
            if self._total_usd + planned_call_usd > self.ceiling_usd:
                raise CeilingExceeded(
                    session_total_usd=self._total_usd,
                    ceiling_usd=self.ceiling_usd,
                    would_have_added_usd=planned_call_usd,
                )

    def record_billed(self, billed_usd: float) -> None:
        """Add an actually-billed cost to the running total."""
        with self._lock:
            self._total_usd += max(0.0, billed_usd)

    def reset(self) -> None:
        """Reset the running total. For tests; do not use in production."""
        with self._lock:
            self._total_usd = 0.0


__all__ = [
    "CeilingExceeded",
    "CostEstimate",
    "PriceTable",
    "PricingError",
    "SessionLedger",
    "estimate_call",
    "load_default",
    "load_from_path",
]
