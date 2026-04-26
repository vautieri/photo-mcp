"""Structured JSON-line logging to stderr.

Per NFR-6.1..6.3: every log line is a single JSON object on stderr; stdout
is reserved for the MCP protocol channel and MUST NOT carry log output.

The logger also redacts secrets — any string starting with ``sk-`` (OpenAI
key prefix) and any field named ``api_key`` / ``Authorization`` / ``auth`` /
``token`` / ``secret`` is replaced with a fixed placeholder before emit.

This module imports nothing from the rest of the package, so any module
may import the logger without creating a cycle.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from collections.abc import Mapping
from typing import Any, Final, Literal

LogLevel = Literal["debug", "info", "warning", "error"]

_LEVEL_ORDER: Final[dict[LogLevel, int]] = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
}

_REDACTED: Final = "<redacted>"
_KEY_PATTERN: Final = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")
_REDACT_FIELD_NAMES: Final = frozenset(
    {"api_key", "authorization", "Authorization", "auth", "token", "secret"}
)


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


class StructuredLogger:
    """Single-process JSON-line logger.

    Thread-safe via a module-level lock around the stderr write so log
    lines never interleave. Output is one JSON object per line; trailing
    ``\\n`` is appended explicitly to avoid platform default-newline
    surprises (Windows otherwise emits ``\\r\\n``).

    Construction is cheap; one instance per module is typical, but a
    process-wide singleton via :func:`get_logger` is the standard path.
    """

    __slots__ = ("_min_level", "_lock", "_static_fields")

    def __init__(
        self,
        *,
        min_level: LogLevel = "info",
        static_fields: Mapping[str, Any] | None = None,
    ) -> None:
        self._min_level = min_level
        self._lock = threading.Lock()
        self._static_fields: dict[str, Any] = dict(static_fields or {})

    # ----- mutators -------------------------------------------------------

    def set_level(self, level: LogLevel) -> None:
        self._min_level = level

    def bind(self, **fields: Any) -> StructuredLogger:
        """Return a child logger that always emits the given static fields."""
        merged = dict(self._static_fields)
        merged.update(fields)
        child = StructuredLogger(min_level=self._min_level, static_fields=merged)
        return child

    # ----- emission -------------------------------------------------------

    def debug(self, event: str, **fields: Any) -> None:
        self._emit("debug", event, fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit("info", event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit("warning", event, fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit("error", event, fields)

    # ----- internals ------------------------------------------------------

    def _emit(self, level: LogLevel, event: str, fields: Mapping[str, Any]) -> None:
        if _LEVEL_ORDER[level] < _LEVEL_ORDER[self._min_level]:
            return
        record: dict[str, Any] = {
            "ts": _utc_now_iso(),
            "level": level,
            "event": event,
        }
        record.update(self._static_fields)
        record.update(fields)
        redacted = redact(record)
        line = json.dumps(redacted, separators=(",", ":"), default=_default_encoder)
        with self._lock:
            sys.stderr.write(line)
            sys.stderr.write("\n")
            sys.stderr.flush()


# -----------------------------------------------------------------------------
# Redaction
# -----------------------------------------------------------------------------


def redact(value: Any) -> Any:
    """Return a deep copy of ``value`` with secrets stripped.

    Rules:
    - Strings matching the OpenAI key prefix pattern (``sk-`` + 8+ chars)
      are replaced wholesale.
    - In dict-like containers, any key in :data:`_REDACT_FIELD_NAMES` has
      its value replaced — without inspecting it.
    - Lists / tuples are walked recursively.
    - Other types are returned as-is (numbers, bools, None, etc.).

    Never raises. Tested in ``tests/security/test_key_redaction.py``.
    """
    if isinstance(value, str):
        return _KEY_PATTERN.sub(_REDACTED, value)
    if isinstance(value, Mapping):
        return {
            k: (_REDACTED if k in _REDACT_FIELD_NAMES else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        cleaned = [redact(v) for v in value]
        return cleaned if isinstance(value, list) else tuple(cleaned)
    return value


# -----------------------------------------------------------------------------
# Module-level singleton
# -----------------------------------------------------------------------------

_root_logger: StructuredLogger | None = None
_root_lock = threading.Lock()


def get_logger() -> StructuredLogger:
    """Return the process-wide logger, creating it on first call.

    Reads ``PHOTO_MCP_LOG_LEVEL`` env var on first call to set the initial
    level (defaults to ``info``). Subsequent ``set_level()`` calls override.
    """
    global _root_logger
    if _root_logger is not None:
        return _root_logger
    with _root_lock:
        if _root_logger is None:
            level_env = os.environ.get("PHOTO_MCP_LOG_LEVEL", "info").lower()
            level: LogLevel = level_env if level_env in _LEVEL_ORDER else "info"  # type: ignore[assignment]
            _root_logger = StructuredLogger(min_level=level)
    return _root_logger


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """ISO-8601 UTC with millisecond precision and trailing 'Z'.

    Avoids ``datetime.utcnow().isoformat()`` because the resulting string
    lacks the trailing 'Z' and parsers that expect strict ISO-8601 reject
    it. We format manually to keep the dependency surface minimal.
    """
    now = time.time()
    secs = int(now)
    millis = int((now - secs) * 1000)
    tm = time.gmtime(secs)
    return (
        f"{tm.tm_year:04d}-{tm.tm_mon:02d}-{tm.tm_mday:02d}T"
        f"{tm.tm_hour:02d}:{tm.tm_min:02d}:{tm.tm_sec:02d}.{millis:03d}Z"
    )


def _default_encoder(obj: Any) -> Any:
    """Fallback for json.dumps when it encounters non-JSON-native types.

    We intentionally degrade gracefully rather than raise — a log-emit
    failure must never disrupt an in-progress tool call. Path objects
    become their string form; bytes become a length marker; anything
    else becomes ``str(obj)``.
    """
    from pathlib import Path

    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, bytes):
        return f"<bytes len={len(obj)}>"
    return str(obj)


__all__ = [
    "LogLevel",
    "StructuredLogger",
    "get_logger",
    "redact",
]
