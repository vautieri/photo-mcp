"""Read-only info tools: ``list_models`` and ``estimate_cost``.

These don't touch the OpenAI API and don't write any files; they
expose the in-process capability matrix and price table to the LLM
client so an agent can plan calls intelligently.
"""

from __future__ import annotations

import json
from typing import Any

from photo_mcp import models
from photo_mcp.cost import PricingError, estimate_call
from photo_mcp.server import ToolContext, ToolDef, ToolResult


# -----------------------------------------------------------------------------
# list_models
# -----------------------------------------------------------------------------


_LIST_MODELS_DESC = """\
List all gpt-image model versions supported by this server, with their
capability matrix. Use this before calling 'generate' or 'edit' to see
which model supports which parameter (sizes, transparent background,
input_fidelity, etc.). The matrix is verified against OpenAI's
published API.

Returns: JSON with one entry per model containing:
- model: identifier (e.g. "gpt-image-2")
- allowed_sizes: list of allowed size strings
- allowed_qualities: list of allowed quality levels
- allowed_output_formats: png/jpeg/webp
- allowed_backgrounds: opaque/auto (and transparent for 1.x)
- supports_input_fidelity: bool (true for 1.x, false for 2)
- max_input_images: 16 (all models)
- max_input_image_bytes: 50 MB (all models)
- max_prompt_chars: 32000 (all models)
- notes: free-form sponsor-facing notes about the model
"""


_LIST_MODELS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}


async def _list_models(_ctx: ToolContext, _args: dict[str, Any]) -> ToolResult:
    matrix = []
    for cap in models.all_capabilities():
        matrix.append({
            "model": cap.model,
            "allowed_sizes": list(cap.allowed_sizes),
            "allowed_qualities": list(cap.allowed_qualities),
            "allowed_output_formats": list(cap.allowed_output_formats),
            "allowed_backgrounds": list(cap.allowed_backgrounds),
            "allowed_moderations": list(cap.allowed_moderations),
            # No response_format choice for gpt-image (DALL-E-only parameter);
            # always returns base64.
            "always_returns_base64": True,
            "supports_input_fidelity": cap.supports_input_fidelity,
            "supports_streaming": cap.supports_streaming,
            "supports_partial_images": cap.supports_partial_images,
            "supports_output_compression": cap.supports_output_compression,
            "max_input_images": cap.max_input_images,
            "max_input_image_bytes": cap.max_input_image_bytes,
            "max_prompt_chars": cap.max_prompt_chars,
            "notes": list(cap.notes),
        })
    payload = {"models": matrix}
    return ToolResult(text=json.dumps(payload, indent=2), structured_payload=payload)


LIST_MODELS_TOOL = ToolDef(
    name="list_models",
    description=_LIST_MODELS_DESC,
    input_schema=_LIST_MODELS_SCHEMA,
    handler=_list_models,
)


# -----------------------------------------------------------------------------
# estimate_cost
# -----------------------------------------------------------------------------


_ESTIMATE_COST_DESC = """\
Estimate the dollar cost of a 'generate' or 'edit' call BEFORE making
it. Useful for budget planning or for confirming that a planned batch
won't exceed the session ceiling.

Inputs:
- model: model identifier (required) — see list_models for valid values
- quality: low | medium | high | auto (default: auto, equivalent to medium)
- size: image size string or "auto"; if "auto", returns 0.0 with is_known=false
        because the API picks the size at call time
- n: number of images (default: 1)

Returns: JSON with:
- model, quality, size, n
- per_image_usd: per-image cost (0.0 if size is "auto")
- total_usd: per_image_usd * n
- is_known: true iff the price table had an entry for this combination
- session_total_usd: running session cost so far
- session_ceiling_usd: configured ceiling (0.0 means no ceiling)

Note: this is an ESTIMATE based on photo-mcp's bundled price table; actual
billing is computed by OpenAI from the call's usage block. The accuracy
target is ±2% (verified during V&V).
"""


_ESTIMATE_COST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "model": {
            "type": "string",
            "description": "Model identifier (gpt-image-1, gpt-image-1-mini, gpt-image-1.5, gpt-image-2)",
        },
        "quality": {
            "type": "string",
            "enum": ["low", "medium", "high", "auto"],
            "default": "auto",
        },
        "size": {
            "type": "string",
            "description": "Image size like '1024x1024' or 'auto'",
            "default": "auto",
        },
        "n": {
            "type": "integer",
            "minimum": 1,
            "default": 1,
        },
    },
    "required": ["model"],
    "additionalProperties": False,
}


async def _estimate_cost(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    model = args.get("model")
    if not isinstance(model, str) or not models.is_known_model(model):
        return _structured_error(
            "unsupported_parameter",
            f"unknown or missing 'model'; expected one of {list(models.ALL_MODELS)}",
        )
    quality = args.get("quality", "auto")
    size = args.get("size", "auto")
    n = int(args.get("n", 1))
    try:
        e = estimate_call(
            table=ctx.price_table,
            model=model,  # type: ignore[arg-type]
            quality=quality,
            size=size,
            n=n,
        )
    except (PricingError, ValueError) as ex:
        return _structured_error("invalid_request", str(ex))
    payload = {
        "model": e.model,
        "quality": e.quality,
        "size": e.size,
        "n": e.n,
        "per_image_usd": round(e.per_image_usd, 6),
        "total_usd": round(e.total_usd, 6),
        "is_known": e.is_known,
        "session_total_usd": round(ctx.session_ledger.total_usd, 6),
        "session_ceiling_usd": ctx.config.session_cost_ceiling_usd,
    }
    return ToolResult(text=json.dumps(payload, indent=2), structured_payload=payload)


ESTIMATE_COST_TOOL = ToolDef(
    name="estimate_cost",
    description=_ESTIMATE_COST_DESC,
    input_schema=_ESTIMATE_COST_SCHEMA,
    handler=_estimate_cost,
)


# -----------------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------------


def _structured_error(error_type: str, message: str) -> ToolResult:
    payload = {"error": {"type": error_type, "message": message}}
    return ToolResult(
        text=json.dumps(payload, indent=2),
        is_error=True,
        structured_payload=payload,
    )


__all__ = ["ESTIMATE_COST_TOOL", "LIST_MODELS_TOOL"]
