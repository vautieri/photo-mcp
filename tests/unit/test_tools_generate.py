"""Tests for the ``generate`` tool.

Covers input validation, capability rejection, atomic write, sidecar
emission, and cost-ceiling enforcement. The OpenAI client is replaced
by an in-test fake that returns scripted base64 PNG bytes — so these
tests run without any network or API key.
"""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from photo_mcp import sidecar
from photo_mcp.config import Config
from photo_mcp.cost import SessionLedger, load_default
from photo_mcp.logging import StructuredLogger
from photo_mcp.openai_client import (
    ApiUsage,
    GenerationRequest,
    ImageData,
    ImageResponse,
)
from photo_mcp.server import ToolContext
from photo_mcp.tools import generate


# -----------------------------------------------------------------------------
# Fake OpenAI client
# -----------------------------------------------------------------------------


def _png_bytes(width: int, height: int, color: tuple[int, int, int] = (60, 90, 200)) -> bytes:
    from PIL import Image
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@dataclass(slots=True)
class FakeOpenAI:
    """Stand-in that mimics ``OpenAIImageClient`` enough for tool tests."""

    images_to_return: list[bytes]
    last_request: GenerationRequest | None = None
    raises: BaseException | None = None

    async def generate(self, req: GenerationRequest) -> ImageResponse:
        self.last_request = req
        if self.raises is not None:
            raise self.raises
        images = [
            ImageData(b64_json=base64.b64encode(b).decode("ascii"))
            for b in self.images_to_return
        ]
        return ImageResponse(
            images=images,
            usage=ApiUsage(input_tokens=10, output_tokens=20, total_tokens=30),
            model=req.model,
            request_ms=42,
        )

    async def edit(self, req: Any) -> Any:  # pragma: no cover — generate-only fake
        raise NotImplementedError


@pytest.fixture
def ctx_factory(tmp_path: Path) -> Any:
    def _make(*, fake: FakeOpenAI, ceiling: float = 0.0) -> ToolContext:
        return ToolContext(
            config=Config(
                api_key="sk-test",
                allowed_input_roots=(tmp_path,),
                allowed_output_roots=(tmp_path,),
                session_cost_ceiling_usd=ceiling,
            ),
            logger=StructuredLogger(min_level="error"),
            price_table=load_default(),
            session_ledger=SessionLedger(ceiling_usd=ceiling),
            openai_client=fake,  # type: ignore[arg-type]
        )
    return _make


# -----------------------------------------------------------------------------
# Happy path
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_writes_output_and_sidecar(
    ctx_factory: Any, tmp_path: Path
) -> None:
    fake = FakeOpenAI(images_to_return=[_png_bytes(64, 64)])
    ctx = ctx_factory(fake=fake)
    result = await generate.GENERATE_TOOL.handler(
        ctx,
        {
            "prompt": "a sunset",
            "model": "gpt-image-2",
            "output_dir": str(tmp_path),
            "output_basename": "out.png",
            "size": "1024x1024",
            "quality": "high",
        },
    )
    assert not result.is_error, result.text

    payload = json.loads(result.text)
    assert payload["model"] == "gpt-image-2"
    assert len(payload["files"]) == 1
    out_path = Path(payload["files"][0])
    assert out_path.exists()

    # Sidecar must exist and be parseable + reference the output's SHA-256
    sc_path = sidecar.sidecar_path_for(out_path)
    assert sc_path.exists()
    sc_data = json.loads(sc_path.read_text(encoding="utf-8"))
    assert sc_data["tool"] == "generate"
    assert sc_data["model"] == "gpt-image-2"
    assert sc_data["prompt"] == "a sunset"
    assert sc_data["output"]["sha256"] == sidecar.hash_file(out_path)
    assert sc_data["sources"] == []  # generate has no sources


@pytest.mark.asyncio
async def test_generate_n_appends_zero_padded_suffix(
    ctx_factory: Any, tmp_path: Path
) -> None:
    fake = FakeOpenAI(images_to_return=[_png_bytes(32, 32) for _ in range(3)])
    ctx = ctx_factory(fake=fake)
    result = await generate.GENERATE_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "n": 3,
            "output_dir": str(tmp_path),
            "output_basename": "img.png",
        },
    )
    payload = json.loads(result.text)
    names = sorted(Path(p).name for p in payload["files"])
    assert names == ["img-1.png", "img-2.png", "img-3.png"]


# -----------------------------------------------------------------------------
# Validation failures
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_rejects_empty_prompt(ctx_factory: Any, tmp_path: Path) -> None:
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[]))
    result = await generate.GENERATE_TOOL.handler(
        ctx,
        {"prompt": "", "model": "gpt-image-2",
         "output_dir": str(tmp_path), "output_basename": "o.png"},
    )
    assert result.is_error
    assert json.loads(result.text)["error"]["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_generate_rejects_unknown_model(ctx_factory: Any, tmp_path: Path) -> None:
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[]))
    result = await generate.GENERATE_TOOL.handler(
        ctx,
        {"prompt": "x", "model": "dall-e-3",
         "output_dir": str(tmp_path), "output_basename": "o.png"},
    )
    assert result.is_error
    assert json.loads(result.text)["error"]["type"] == "unsupported_parameter"


@pytest.mark.asyncio
async def test_generate_rejects_4k_on_gpt_image_1(
    ctx_factory: Any, tmp_path: Path
) -> None:
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[]))
    result = await generate.GENERATE_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "model": "gpt-image-1",  # 1.x doesn't support 4K
            "size": "3840x2160",
            "output_dir": str(tmp_path),
            "output_basename": "o.png",
        },
    )
    assert result.is_error
    assert json.loads(result.text)["error"]["type"] == "unsupported_parameter"


@pytest.mark.asyncio
async def test_generate_rejects_transparent_on_gpt_image_2(
    ctx_factory: Any, tmp_path: Path
) -> None:
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[]))
    result = await generate.GENERATE_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "model": "gpt-image-2",
            "background": "transparent",
            "size": "1024x1024",
            "output_dir": str(tmp_path),
            "output_basename": "o.png",
        },
    )
    assert result.is_error
    err = json.loads(result.text)["error"]
    assert err["type"] == "unsupported_parameter"


@pytest.mark.asyncio
async def test_generate_refuses_overwriting_existing(
    ctx_factory: Any, tmp_path: Path
) -> None:
    target = tmp_path / "exists.png"
    target.write_bytes(b"prior")
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[_png_bytes(8, 8)]))
    result = await generate.GENERATE_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "exists.png",
        },
    )
    assert result.is_error
    assert json.loads(result.text)["error"]["type"] == "output_exists"


@pytest.mark.asyncio
async def test_generate_overwrite_true_replaces(ctx_factory: Any, tmp_path: Path) -> None:
    target = tmp_path / "exists.png"
    target.write_bytes(b"prior")
    new_png = _png_bytes(8, 8)
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[new_png]))
    result = await generate.GENERATE_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "exists.png",
            "overwrite": True,
        },
    )
    assert not result.is_error
    assert target.read_bytes() == new_png


# -----------------------------------------------------------------------------
# Cost ceiling
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_refuses_when_ceiling_exceeded(
    ctx_factory: Any, tmp_path: Path
) -> None:
    """Set ceiling to 0.001 — way below any real call's cost — and expect refusal."""
    ctx = ctx_factory(
        fake=FakeOpenAI(images_to_return=[_png_bytes(8, 8)]),
        ceiling=0.001,
    )
    result = await generate.GENERATE_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "o.png",
        },
    )
    assert result.is_error
    err = json.loads(result.text)["error"]
    assert err["type"] == "cost_ceiling"
    assert "ceiling_usd" in err
    assert "session_total_usd" in err
    assert "would_have_added_usd" in err


# -----------------------------------------------------------------------------
# Path safety
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_rejects_output_outside_allowed_root(
    ctx_factory: Any, tmp_path: Path
) -> None:
    other = tmp_path.parent / "elsewhere"
    other.mkdir(exist_ok=True)
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[]))
    # Output dir is outside ctx.allowed_output_roots (which is tmp_path).
    result = await generate.GENERATE_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(other),
            "output_basename": "o.png",
        },
    )
    assert result.is_error
    err = json.loads(result.text)["error"]
    assert err["type"] in {"path_outside_roots", "path_does_not_exist"}
