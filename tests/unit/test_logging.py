"""Logging redaction + JSON-line format tests.

NFR-3.2: API key never appears in log output.
NFR-6.1..6.3: JSON-per-line on stderr; stdout untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from photo_mcp import logging as plog


# -----------------------------------------------------------------------------
# Redaction
# -----------------------------------------------------------------------------


def test_redact_strips_openai_key_in_string() -> None:
    out = plog.redact("call with sk-AB12cd34EF56gh78 inline")
    assert "sk-AB12cd34EF56gh78" not in out  # type: ignore[operator]
    assert "<redacted>" in out


def test_redact_strips_in_nested_dict() -> None:
    inp: dict[str, Any] = {
        "url": "https://api.openai.com/v1/...",
        "headers": {
            "Authorization": "Bearer sk-AB12cd34EF56gh78",
            "User-Agent": "photo-mcp/0.1",
        },
        "body": {"prompt": "a sk-realistic-painting on the wall"},
    }
    out = plog.redact(inp)
    # Authorization field redacted regardless of contents.
    assert out["headers"]["Authorization"] == "<redacted>"
    # User-Agent left alone.
    assert out["headers"]["User-Agent"] == "photo-mcp/0.1"
    # The string in body was redacted because of the sk- prefix pattern.
    body_prompt: str = out["body"]["prompt"]
    assert "<redacted>" in body_prompt or "sk-realistic-painting" not in body_prompt


def test_redact_handles_lists() -> None:
    out = plog.redact(["safe", "sk-AB12cd34EF56gh78", 42])
    assert out[0] == "safe"
    assert "<redacted>" in out[1]  # type: ignore[operator]
    assert out[2] == 42


def test_redact_field_names_include_token_and_secret() -> None:
    inp = {"api_key": "x", "token": "y", "secret": "z", "auth": "w", "ok": "value"}
    out = plog.redact(inp)
    for k in ("api_key", "token", "secret", "auth"):
        assert out[k] == "<redacted>"
    assert out["ok"] == "value"


def test_redact_does_not_mangle_normal_strings() -> None:
    assert plog.redact("ordinary message") == "ordinary message"
    assert plog.redact("") == ""


def test_redact_preserves_primitive_types() -> None:
    assert plog.redact(42) == 42
    assert plog.redact(3.14) == 3.14
    assert plog.redact(True) is True
    assert plog.redact(None) is None


# -----------------------------------------------------------------------------
# Logger emission
# -----------------------------------------------------------------------------


def test_emits_json_per_line(capsys: pytest.CaptureFixture[str]) -> None:
    log = plog.StructuredLogger(min_level="info")
    log.info("call_made", model="gpt-image-2", latency_ms=42)
    log.info("call_made", model="gpt-image-1.5", latency_ms=80)
    captured = capsys.readouterr()
    lines = [ln for ln in captured.err.splitlines() if ln]
    assert len(lines) == 2
    parsed = [json.loads(ln) for ln in lines]
    assert parsed[0]["event"] == "call_made"
    assert parsed[0]["model"] == "gpt-image-2"
    assert parsed[0]["level"] == "info"
    assert "ts" in parsed[0]


def test_log_level_filters_below(capsys: pytest.CaptureFixture[str]) -> None:
    log = plog.StructuredLogger(min_level="warning")
    log.debug("ignored")
    log.info("ignored")
    log.warning("kept")
    log.error("kept2")
    captured = capsys.readouterr()
    lines = [ln for ln in captured.err.splitlines() if ln]
    assert len(lines) == 2
    events = [json.loads(ln)["event"] for ln in lines]
    assert events == ["kept", "kept2"]


def test_log_redacts_api_key_field(capsys: pytest.CaptureFixture[str]) -> None:
    log = plog.StructuredLogger(min_level="info")
    log.info("auth_failed", api_key="sk-should-not-appear", reason="401")
    line = capsys.readouterr().err.strip()
    assert "sk-should-not-appear" not in line
    parsed = json.loads(line)
    assert parsed["api_key"] == "<redacted>"
    assert parsed["reason"] == "401"


def test_bind_attaches_static_fields(capsys: pytest.CaptureFixture[str]) -> None:
    base = plog.StructuredLogger(min_level="info")
    child = base.bind(call_id="c-123", model="gpt-image-2")
    child.info("event_a")
    parsed = json.loads(capsys.readouterr().err.strip())
    assert parsed["call_id"] == "c-123"
    assert parsed["model"] == "gpt-image-2"


def test_bind_does_not_mutate_parent(capsys: pytest.CaptureFixture[str]) -> None:
    base = plog.StructuredLogger(min_level="info")
    child = base.bind(extra="ok")
    base.info("from_base")
    child.info("from_child")
    lines = [json.loads(ln) for ln in capsys.readouterr().err.splitlines() if ln]
    assert "extra" not in lines[0]
    assert lines[1]["extra"] == "ok"


def test_path_objects_serialize_as_strings(capsys: pytest.CaptureFixture[str]) -> None:
    log = plog.StructuredLogger(min_level="info")
    log.info("wrote", out=Path("/tmp/x.png"))
    parsed = json.loads(capsys.readouterr().err.strip())
    assert parsed["out"] == "/tmp/x.png" or parsed["out"].endswith("x.png")


def test_does_not_write_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    log = plog.StructuredLogger(min_level="info")
    log.info("event")
    captured = capsys.readouterr()
    # Logger MUST only write to stderr; stdout is the MCP protocol channel.
    assert captured.out == ""
    assert captured.err.strip() != ""  # something landed on stderr


def test_iso_timestamp_has_z_suffix(capsys: pytest.CaptureFixture[str]) -> None:
    log = plog.StructuredLogger(min_level="info")
    log.info("e")
    ts = json.loads(capsys.readouterr().err.strip())["ts"]
    assert ts.endswith("Z")
    # Format: YYYY-MM-DDTHH:MM:SS.mmmZ
    assert len(ts) == 24
    assert ts[10] == "T"


# -----------------------------------------------------------------------------
# get_logger singleton
# -----------------------------------------------------------------------------


def test_get_logger_returns_singleton() -> None:
    a = plog.get_logger()
    b = plog.get_logger()
    assert a is b
