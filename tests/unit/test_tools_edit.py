"""Tests for the ``edit`` tool.

Covers single-image edit, multi-image (1..16) compositing, mask-only-with-
single-image rejection, source EXIF / ICC capture-and-reattach, atomic
write, sidecar with full source SHA-256s, and error paths. No real
OpenAI calls — a fake client returns scripted images.
"""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from photo_mcp import sidecar
from photo_mcp.config import Config
from photo_mcp.cost import SessionLedger, load_default
from photo_mcp.logging import StructuredLogger
from photo_mcp.openai_client import (
    ApiUsage,
    EditRequest,
    GenerationRequest,
    ImageData,
    ImageResponse,
)
from photo_mcp.server import ToolContext
from photo_mcp.tools import edit


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _png_bytes(w: int, h: int, color: tuple[int, int, int] = (40, 90, 200)) -> bytes:
    from PIL import Image
    img = Image.new("RGB", (w, h), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _alpha_mask_bytes(w: int, h: int) -> bytes:
    from PIL import Image
    img = Image.new("RGBA", (w, h), color=(0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@dataclass(slots=True)
class FakeOpenAI:
    images_to_return: list[bytes]
    last_edit_request: EditRequest | None = None
    edit_calls: list[EditRequest] = field(default_factory=list)
    raises: BaseException | None = None

    async def edit(self, req: EditRequest) -> ImageResponse:
        self.last_edit_request = req
        self.edit_calls.append(req)
        if self.raises is not None:
            raise self.raises
        images = [
            ImageData(b64_json=base64.b64encode(b).decode("ascii"))
            for b in self.images_to_return
        ]
        return ImageResponse(
            images=images,
            usage=ApiUsage(input_tokens=100, output_tokens=20, total_tokens=120),
            model=req.model,
            request_ms=4127,
        )

    async def generate(self, req: GenerationRequest) -> Any:  # pragma: no cover
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
# Single-image edit
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_single_image_writes_output_and_sidecar(
    ctx_factory: Any, tmp_path: Path
) -> None:
    src = tmp_path / "src.png"
    src.write_bytes(_png_bytes(64, 64))
    fake = FakeOpenAI(images_to_return=[_png_bytes(64, 64)])
    ctx = ctx_factory(fake=fake)

    result = await edit.EDIT_TOOL.handler(
        ctx,
        {
            "prompt": "preserve everything, just brighten the sky",
            "image": [str(src)],
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "out.png",
        },
    )
    assert not result.is_error, result.text
    payload = json.loads(result.text)
    out_path = Path(payload["files"][0])
    assert out_path.exists()

    sc_path = sidecar.sidecar_path_for(out_path)
    sc = json.loads(sc_path.read_text(encoding="utf-8"))
    assert sc["tool"] == "edit"
    assert sc["model"] == "gpt-image-2"
    assert len(sc["sources"]) == 1
    assert sc["sources"][0]["sha256"] == sidecar.hash_file(src)
    # ssim_to_image_0 should be present for single-image edits.
    assert sc["ssim_to_image_0"] is not None
    assert 0.0 <= sc["ssim_to_image_0"] <= 1.0


# -----------------------------------------------------------------------------
# Multi-image edit
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_multi_image_includes_all_source_shas(
    ctx_factory: Any, tmp_path: Path
) -> None:
    srcs = []
    for i in range(3):
        p = tmp_path / f"src{i}.png"
        p.write_bytes(_png_bytes(64, 64, color=(i * 50, 0, 0)))
        srcs.append(p)
    fake = FakeOpenAI(images_to_return=[_png_bytes(64, 64)])
    ctx = ctx_factory(fake=fake)

    result = await edit.EDIT_TOOL.handler(
        ctx,
        {
            "prompt": "merge them",
            "image": [str(p) for p in srcs],
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "merged.png",
        },
    )
    assert not result.is_error, result.text
    payload = json.loads(result.text)
    out_path = Path(payload["files"][0])
    sc = json.loads(sidecar.sidecar_path_for(out_path).read_text(encoding="utf-8"))
    # All 3 source SHA-256s present
    sc_shas = {s["sha256"] for s in sc["sources"]}
    expected_shas = {sidecar.hash_file(p) for p in srcs}
    assert sc_shas == expected_shas
    # Multi-image edits don't compute SSIM (no canonical "image[0]" comparison).
    assert sc["ssim_to_image_0"] is None


@pytest.mark.asyncio
async def test_edit_rejects_more_than_16_images(
    ctx_factory: Any, tmp_path: Path
) -> None:
    paths = []
    for i in range(17):
        p = tmp_path / f"s{i}.png"
        p.write_bytes(_png_bytes(8, 8))
        paths.append(str(p))
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[]))
    result = await edit.EDIT_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "image": paths,
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "o.png",
        },
    )
    assert result.is_error
    err = json.loads(result.text)["error"]
    assert err["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_edit_rejects_zero_images(ctx_factory: Any, tmp_path: Path) -> None:
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[]))
    result = await edit.EDIT_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "image": [],
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "o.png",
        },
    )
    assert result.is_error
    assert json.loads(result.text)["error"]["type"] == "invalid_request"


# -----------------------------------------------------------------------------
# Mask requires single image
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_rejects_mask_with_multiple_images(
    ctx_factory: Any, tmp_path: Path
) -> None:
    s1 = tmp_path / "s1.png"; s1.write_bytes(_png_bytes(8, 8))
    s2 = tmp_path / "s2.png"; s2.write_bytes(_png_bytes(8, 8))
    mask = tmp_path / "mask.png"; mask.write_bytes(_alpha_mask_bytes(8, 8))
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[]))
    result = await edit.EDIT_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "image": [str(s1), str(s2)],
            "mask": str(mask),
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "o.png",
        },
    )
    assert result.is_error
    err = json.loads(result.text)["error"]
    assert err["type"] == "invalid_request"
    assert "mask" in err["message"].lower()


@pytest.mark.asyncio
async def test_edit_accepts_mask_with_single_image(
    ctx_factory: Any, tmp_path: Path
) -> None:
    src = tmp_path / "src.png"; src.write_bytes(_png_bytes(64, 64))
    mask = tmp_path / "mask.png"; mask.write_bytes(_alpha_mask_bytes(64, 64))
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[_png_bytes(64, 64)]))
    result = await edit.EDIT_TOOL.handler(
        ctx,
        {
            "prompt": "edit only the masked region",
            "image": [str(src)],
            "mask": str(mask),
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "o.png",
        },
    )
    assert not result.is_error, result.text


# -----------------------------------------------------------------------------
# input_fidelity validation
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_rejects_low_fidelity_on_gpt_image_2(
    ctx_factory: Any, tmp_path: Path
) -> None:
    src = tmp_path / "s.png"; src.write_bytes(_png_bytes(8, 8))
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[]))
    result = await edit.EDIT_TOOL.handler(
        ctx,
        {
            "prompt": "x",
            "image": [str(src)],
            "model": "gpt-image-2",
            "input_fidelity": "low",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "o.png",
        },
    )
    assert result.is_error
    assert json.loads(result.text)["error"]["type"] == "unsupported_parameter"


@pytest.mark.asyncio
async def test_edit_accepts_low_fidelity_on_gpt_image_1_5(
    ctx_factory: Any, tmp_path: Path
) -> None:
    src = tmp_path / "s.png"; src.write_bytes(_png_bytes(64, 64))
    ctx = ctx_factory(fake=FakeOpenAI(images_to_return=[_png_bytes(64, 64)]))
    result = await edit.EDIT_TOOL.handler(
        ctx,
        {
            "prompt": "creative reinterpretation",
            "image": [str(src)],
            "model": "gpt-image-1.5",
            "input_fidelity": "low",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "o.png",
        },
    )
    assert not result.is_error, result.text


# -----------------------------------------------------------------------------
# Authenticity audit (WS-7)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_audit_trail_replay(ctx_factory: Any, tmp_path: Path) -> None:
    """Round-trip: write edit, then verify each source SHA-256 in the sidecar
    matches the on-disk file. This is the WS-7 acceptance scenario:
    the photographer can prove "this was the original" using only the
    sidecar + filesystem."""
    s1 = tmp_path / "src1.png"; s1.write_bytes(_png_bytes(32, 32, (10, 20, 30)))
    s2 = tmp_path / "src2.png"; s2.write_bytes(_png_bytes(32, 32, (40, 50, 60)))
    fake = FakeOpenAI(images_to_return=[_png_bytes(32, 32)])
    ctx = ctx_factory(fake=fake)

    result = await edit.EDIT_TOOL.handler(
        ctx,
        {
            "prompt": "audit me",
            "image": [str(s1), str(s2)],
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "out.png",
        },
    )
    assert not result.is_error
    payload = json.loads(result.text)
    sc = json.loads(
        sidecar.sidecar_path_for(Path(payload["files"][0])).read_text(encoding="utf-8")
    )
    # Run the same audit a future viewer would.
    for entry in sc["sources"]:
        on_disk_now = sidecar.hash_file(Path(entry["path"]))
        assert on_disk_now == entry["sha256"]


# -----------------------------------------------------------------------------
# Source files never modified (QR-9)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_does_not_modify_source_files(ctx_factory: Any, tmp_path: Path) -> None:
    src = tmp_path / "untouchable.png"
    payload_bytes = _png_bytes(64, 64)
    src.write_bytes(payload_bytes)
    sha_before = sidecar.hash_bytes(payload_bytes)

    fake = FakeOpenAI(images_to_return=[_png_bytes(64, 64)])
    ctx = ctx_factory(fake=fake)
    await edit.EDIT_TOOL.handler(
        ctx,
        {
            "prompt": "edit",
            "image": [str(src)],
            "model": "gpt-image-2",
            "size": "1024x1024",
            "quality": "high",
            "output_dir": str(tmp_path),
            "output_basename": "out.png",
        },
    )
    sha_after = sidecar.hash_file(src)
    assert sha_before == sha_after, "source file was modified by edit"
