"""Tests for the read-only info tools (``list_models`` + ``estimate_cost``).

No mocking required — these tools don't touch the OpenAI API; they
read from the in-process capability matrix and price table.
"""

from __future__ import annotations

import json

import pytest

from photo_mcp.config import Config
from photo_mcp.cost import SessionLedger, load_default
from photo_mcp.logging import StructuredLogger
from photo_mcp.server import ToolContext
from photo_mcp.tools import info


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(
        config=Config(api_key="sk-test"),
        logger=StructuredLogger(min_level="error"),
        price_table=load_default(),
        session_ledger=SessionLedger(ceiling_usd=0.0),
        openai_client=None,
    )


# -----------------------------------------------------------------------------
# list_models
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models_returns_all_four(ctx: ToolContext) -> None:
    result = await info.LIST_MODELS_TOOL.handler(ctx, {})
    assert not result.is_error
    payload = json.loads(result.text)
    names = [m["model"] for m in payload["models"]]
    assert names == [
        "gpt-image-1",
        "gpt-image-1-mini",
        "gpt-image-1.5",
        "gpt-image-2",
    ]


@pytest.mark.asyncio
async def test_list_models_includes_critical_capabilities(ctx: ToolContext) -> None:
    result = await info.LIST_MODELS_TOOL.handler(ctx, {})
    payload = json.loads(result.text)
    by_name = {m["model"]: m for m in payload["models"]}

    # gpt-image-2 capability check (the headline differences from 1.x)
    g2 = by_name["gpt-image-2"]
    assert "3840x2160" in g2["allowed_sizes"]
    assert "transparent" not in g2["allowed_backgrounds"]
    assert g2["supports_input_fidelity"] is False

    # gpt-image-1.5 supports input_fidelity + transparent
    g15 = by_name["gpt-image-1.5"]
    assert g15["supports_input_fidelity"] is True
    assert "transparent" in g15["allowed_backgrounds"]
    assert "3840x2160" not in g15["allowed_sizes"]


@pytest.mark.asyncio
async def test_list_models_max_inputs_consistent(ctx: ToolContext) -> None:
    """All models cap at 16 input images per docs/02-requirements.md §6."""
    result = await info.LIST_MODELS_TOOL.handler(ctx, {})
    payload = json.loads(result.text)
    for m in payload["models"]:
        assert m["max_input_images"] == 16
        assert m["max_input_image_bytes"] == 50 * 1024 * 1024
        assert m["max_prompt_chars"] == 32_000


@pytest.mark.asyncio
async def test_list_models_returns_structured_payload(ctx: ToolContext) -> None:
    result = await info.LIST_MODELS_TOOL.handler(ctx, {})
    assert result.structured_payload is not None
    assert "models" in result.structured_payload


# -----------------------------------------------------------------------------
# estimate_cost
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_cost_known_combo(ctx: ToolContext) -> None:
    result = await info.ESTIMATE_COST_TOOL.handler(
        ctx,
        {"model": "gpt-image-2", "quality": "high", "size": "1024x1024", "n": 2},
    )
    assert not result.is_error
    payload = json.loads(result.text)
    assert payload["model"] == "gpt-image-2"
    assert payload["n"] == 2
    assert payload["per_image_usd"] > 0
    assert payload["total_usd"] == pytest.approx(payload["per_image_usd"] * 2)
    assert payload["is_known"] is True


@pytest.mark.asyncio
async def test_estimate_cost_auto_size_unknown(ctx: ToolContext) -> None:
    result = await info.ESTIMATE_COST_TOOL.handler(
        ctx, {"model": "gpt-image-2", "size": "auto", "quality": "high"}
    )
    payload = json.loads(result.text)
    assert payload["is_known"] is False
    assert payload["total_usd"] == 0.0


@pytest.mark.asyncio
async def test_estimate_cost_unknown_model_rejected(ctx: ToolContext) -> None:
    result = await info.ESTIMATE_COST_TOOL.handler(ctx, {"model": "dall-e-3"})
    assert result.is_error
    payload = json.loads(result.text)
    assert payload["error"]["type"] == "unsupported_parameter"


@pytest.mark.asyncio
async def test_estimate_cost_missing_model_rejected(ctx: ToolContext) -> None:
    result = await info.ESTIMATE_COST_TOOL.handler(ctx, {})
    assert result.is_error
    assert json.loads(result.text)["error"]["type"] == "unsupported_parameter"


@pytest.mark.asyncio
async def test_estimate_cost_includes_session_total(ctx: ToolContext) -> None:
    ctx.session_ledger.record_billed(2.5)
    result = await info.ESTIMATE_COST_TOOL.handler(
        ctx, {"model": "gpt-image-2", "quality": "high", "size": "1024x1024"}
    )
    payload = json.loads(result.text)
    assert payload["session_total_usd"] == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_estimate_cost_n_validates(ctx: ToolContext) -> None:
    """n=0 is an invalid request — the underlying estimator raises ValueError;
    the tool surfaces it as a structured error."""
    result = await info.ESTIMATE_COST_TOOL.handler(
        ctx,
        {"model": "gpt-image-2", "quality": "high", "size": "1024x1024", "n": 0},
    )
    assert result.is_error
    assert json.loads(result.text)["error"]["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_estimate_cost_quality_auto_resolves_to_medium_price(ctx: ToolContext) -> None:
    """The cost module documents 'auto' resolves to 'medium' for estimation."""
    auto = json.loads((await info.ESTIMATE_COST_TOOL.handler(
        ctx, {"model": "gpt-image-2", "quality": "auto", "size": "1024x1024"}
    )).text)
    medium = json.loads((await info.ESTIMATE_COST_TOOL.handler(
        ctx, {"model": "gpt-image-2", "quality": "medium", "size": "1024x1024"}
    )).text)
    assert auto["per_image_usd"] == medium["per_image_usd"]
