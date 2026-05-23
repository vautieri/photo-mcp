"""Tests for the progressive imaging path — stream consumption + the
optional progress_emitter callback fired once per partial frame.

The streaming code in ``tools/edit.py`` and ``tools/generate.py``
already collects partial frames into the final tool result (the
``partials`` array). 2026-05-22 added a second consumer: an optional
``progress_emitter`` bound by ``PhotoMcpServer._build_progress_emitter``
when the MCP client sends a ``progressToken``. The emitter fires one
MCP ``notifications/progress`` per partial so the bridge can forward
a progressive preview as an SSE event.

These tests pin the contract of ``_consume_edit_stream`` /
``_consume_generate_stream`` — partials still land in the tool
result (LLM-visible) AND the progress_emitter fires once per partial
when supplied, with the expected payload shape. The
``progressToken``-not-supplied path (emitter=None) is covered too: the
tool result must be unchanged so no behavior regression for clients
that don't opt in.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import pytest

from photo_mcp.openai_client import (
    ApiUsage,
    EditRequest,
    GenerationRequest,
    StreamEvent,
)
from photo_mcp.tools.edit import _consume_edit_stream
from photo_mcp.tools.generate import _consume_generate_stream


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode("ascii")


@dataclass(slots=True)
class FakeStreamingClient:
    """Yields a scripted sequence of StreamEvents from stream_edit/stream_generate."""

    events: list[StreamEvent]
    last_edit_request: EditRequest | None = None
    last_generate_request: GenerationRequest | None = None

    async def stream_edit(self, req: EditRequest) -> Any:
        self.last_edit_request = req
        for ev in self.events:
            yield ev

    async def stream_generate(self, req: GenerationRequest) -> Any:
        self.last_generate_request = req
        for ev in self.events:
            yield ev


@dataclass(slots=True)
class RecordingEmitter:
    """Captures every progress_emitter call for later inspection."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(
        self,
        *,
        index: int,
        total: int,
        b64_json: str,
        mime_type: str,
        revised_prompt: str | None = None,
    ) -> None:
        self.calls.append({
            "index":          index,
            "total":          total,
            "b64_json":       b64_json,
            "mime_type":      mime_type,
            "revised_prompt": revised_prompt,
        })


def _scripted_events(num_partials: int) -> list[StreamEvent]:
    events: list[StreamEvent] = []
    for i in range(num_partials):
        events.append(StreamEvent(
            kind="partial",
            index=i,
            b64_json=_b64(f"partial-{i}"),
            revised_prompt=f"refined prompt {i}",
        ))
    events.append(StreamEvent(
        kind="completed",
        b64_json=_b64("final"),
        revised_prompt="final revised prompt",
        usage=ApiUsage(input_tokens=100, output_tokens=20, total_tokens=120),
    ))
    return events


# -----------------------------------------------------------------------------
# _consume_edit_stream — emitter fires once per partial
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consume_edit_stream_fires_emitter_per_partial() -> None:
    """When a progress_emitter is supplied, it must be called once
    per partial frame with the partial's index, b64, and mime type."""
    fake = FakeStreamingClient(events=_scripted_events(2))
    emitter = RecordingEmitter()

    req = EditRequest(
        model="gpt-image-1.5",
        prompt="edit me",
        image_paths=(),
        n=1,
        partial_images=2,
    )

    response, partials = await _consume_edit_stream(
        fake, req, progress_emitter=emitter, output_format="png",
    )

    # LLM-visible result: partials collected into the structured payload.
    assert len(partials) == 2
    assert partials[0]["b64_json"] == _b64("partial-0")
    assert partials[1]["b64_json"] == _b64("partial-1")

    # Out-of-band emitter: fired once per partial with the right shape.
    assert len(emitter.calls) == 2
    assert emitter.calls[0] == {
        "index":          0,
        "total":          2,
        "b64_json":       _b64("partial-0"),
        "mime_type":      "image/png",
        "revised_prompt": "refined prompt 0",
    }
    assert emitter.calls[1] == {
        "index":          1,
        "total":          2,
        "b64_json":       _b64("partial-1"),
        "mime_type":      "image/png",
        "revised_prompt": "refined prompt 1",
    }

    # Completion synthesized into an ImageResponse shape so the caller's
    # post-stream pipeline (write to disk, sidecar, etc.) runs unchanged.
    assert response is not None
    assert response.images[0].b64_json == _b64("final")
    assert response.usage.total_tokens == 120


@pytest.mark.asyncio
async def test_consume_edit_stream_no_emitter_no_side_effects() -> None:
    """When progress_emitter is None (client didn't request progress)
    the partials still land in the tool result — the LLM-visible behavior
    is identical to before progressive imaging was added."""
    fake = FakeStreamingClient(events=_scripted_events(2))

    req = EditRequest(
        model="gpt-image-1.5",
        prompt="edit me",
        image_paths=(),
        n=1,
        partial_images=2,
    )

    response, partials = await _consume_edit_stream(fake, req, progress_emitter=None)
    assert len(partials) == 2
    assert response is not None


@pytest.mark.asyncio
async def test_consume_edit_stream_mime_type_follows_output_format() -> None:
    """The emitter's mime_type follows the requested output_format so
    the bridge can decode the partial without sniffing. WebP / JPEG
    requests get the matching MIME."""
    fake = FakeStreamingClient(events=_scripted_events(1))
    emitter = RecordingEmitter()

    req = EditRequest(
        model="gpt-image-1.5",
        prompt="edit me",
        image_paths=(),
        n=1,
        partial_images=1,
    )

    await _consume_edit_stream(
        fake, req, progress_emitter=emitter, output_format="webp",
    )
    assert emitter.calls[0]["mime_type"] == "image/webp"


# -----------------------------------------------------------------------------
# _consume_generate_stream — same contract as edit
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consume_generate_stream_fires_emitter_per_partial() -> None:
    fake = FakeStreamingClient(events=_scripted_events(3))
    emitter = RecordingEmitter()

    req = GenerationRequest(
        model="gpt-image-1.5",
        prompt="make me a sunset",
        n=1,
        partial_images=3,
    )

    response, partials = await _consume_generate_stream(
        fake, req, progress_emitter=emitter, output_format="png",
    )

    assert len(partials) == 3
    assert len(emitter.calls) == 3
    assert [c["index"] for c in emitter.calls] == [0, 1, 2]
    assert all(c["total"] == 3 for c in emitter.calls)
    assert all(c["mime_type"] == "image/png" for c in emitter.calls)
    assert response is not None


@pytest.mark.asyncio
async def test_consume_generate_stream_skips_emitter_when_partial_has_no_payload() -> None:
    """Partials without a b64 payload (rare — OpenAI's stream contract
    promises b64 on partial frames but defensive code never trusts a
    network format) must not call the emitter — the emitter expects a
    decodable payload."""
    events = [
        StreamEvent(kind="partial", index=0, b64_json=None),
        StreamEvent(kind="partial", index=1, b64_json=_b64("partial-1")),
        StreamEvent(
            kind="completed",
            b64_json=_b64("final"),
            usage=ApiUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        ),
    ]
    fake = FakeStreamingClient(events=events)
    emitter = RecordingEmitter()

    req = GenerationRequest(
        model="gpt-image-1.5",
        prompt="make me a sunset",
        n=1,
        partial_images=2,
    )

    await _consume_generate_stream(
        fake, req, progress_emitter=emitter, output_format="png",
    )
    # Only the partial with a real b64 fires the emitter.
    assert len(emitter.calls) == 1
    assert emitter.calls[0]["index"] == 1
