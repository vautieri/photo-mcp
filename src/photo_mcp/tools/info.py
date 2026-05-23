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
List every gpt-image model version this server exposes, with its full
capability matrix. Call this BEFORE 'generate' or 'edit' if you need to
pick the right model for a constraint (e.g. transparent background,
4K output, multi-image composite). The matrix is the source of truth
for which parameters that model accepts — call sites that violate it
get a structured 'unsupported_parameter' error pre-flight.

Returns JSON `{models: [...]}` with one entry per model:
- model: identifier (e.g. "gpt-image-2", "gpt-image-1.5", "gpt-image-1",
         "gpt-image-1-mini")
- allowed_sizes: list of accepted size strings ("auto" plus concrete
                 pixel dimensions; gpt-image-2 includes 2K + 4K)
- allowed_qualities: low / medium / high / auto
- allowed_output_formats: png / jpeg / webp
- allowed_backgrounds: opaque / auto (transparent ONLY on gpt-image-1.x,
                       NOT on gpt-image-2)
- allowed_moderations: low / auto
- always_returns_base64: true (the response_format=url DALL-E parameter
                         is rejected by gpt-image; we always get b64)
- supports_input_fidelity: true for 1.x, false for 2 (which is always high)
- supports_streaming: bool — pass `stream=true` on generate/edit
- supports_partial_images: bool — pass `partial_images=N` (0..3) with
                           `stream=true` for progressive previews
- supports_output_compression: bool — pass `output_compression=0..100`
                                for webp/jpeg outputs
- max_input_images: 16 (all gpt-image models accept 1..16 source images
                    on /edit)
- max_input_image_bytes: 50 MB per image (mask cap is 4 MB, enforced
                         pre-flight)
- max_prompt_chars: 32000
- notes: free-form per-model notes (deprecation warnings, sponsor
         availability constraints, etc.)
"""


_LIST_MODELS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}


async def _list_models(_ctx: ToolContext, _args: dict[str, Any]) -> ToolResult:
    allowed = _ctx.config.allowed_models
    matrix = []
    for cap in models.all_capabilities():
        # If operator configured an allowlist, hide other models from the
        # client. The LLM picks from what it sees; if gpt-image-2 isn't
        # exposed, it won't try to call it. This is the primary mechanism
        # for "my org isn't verified for gpt-image-2" — operator sets
        # PHOTO_MCP_ALLOWED_MODELS=gpt-image-1.5,gpt-image-1 and the model
        # never appears in any tool response.
        if allowed and cap.model not in allowed:
            continue
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
            "enum": list(models.ALL_MODELS),
            "description": "Model identifier. Use list_models for full capability matrix.",
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
    # Mirror the allowlist gate from edit/generate. Without this, the LLM can
    # still call estimate_cost with a disallowed model and receive a price —
    # which signals "this model exists" and may prompt it to retry the
    # actual edit/generate call against the gated model.
    if ctx.config.allowed_models and model not in ctx.config.allowed_models:
        return _structured_error(
            "unsupported_parameter",
            f"model {model!r} is not in this server's allowed_models "
            f"set ({list(ctx.config.allowed_models)}). Operator restricted "
            f"the model list (typically because the OpenAI org isn't "
            f"verified for the excluded models).",
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
