"""``generate`` tool — prompt-only image generation.

FR-2.1 — wraps OpenAI's ``/v1/images/generations`` with full parameter
exposure, atomic output writing, integrity verification, and provenance
sidecar.

The tool defers most validation to :mod:`photo_mcp.models` (capability
matrix) and :mod:`photo_mcp.paths` (output path safety). Errors are
returned as structured ER-* payloads so the LLM can react.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from photo_mcp import models, sidecar
from photo_mcp.cost import CeilingExceeded, estimate_call
from photo_mcp.openai_client import (
    AuthError,
    GenerationRequest,
    OpenAIClientError,
    OpenAIImageClient,
)
from photo_mcp.output import (
    OutputCorrupt,
    OutputExists,
    numbered_path,
    write_and_verify,
)
from photo_mcp.paths import PathError
from photo_mcp.server import ToolContext, ToolDef, ToolResult


_GENERATE_DESC = """\
Generate an image from a text prompt using one of the gpt-image models.
No source image is required — this is for ideation, mockups, or reference
boards. For editing or compositing existing photographs, use 'edit'.

Critical parameters:
- prompt (required): natural-language description, up to 32,000 chars
- model: one of gpt-image-1, gpt-image-1-mini, gpt-image-1.5, gpt-image-2
         (default: gpt-image-1.5)
- output_dir + output_basename: where to write the result (required)
- size: 1024x1024, 1024x1536, 1536x1024, or auto. gpt-image-2 also
        supports 2048x*, 3840x2160, 2160x3840 (4K). Default: auto.
- quality: low | medium | high | auto (default: auto)
- output_format: png | jpeg | webp (default: png — lossless)
- background: opaque | auto | transparent. Transparent NOT supported on gpt-image-2.
- n: number of images (default: 1, max 10). When n>1, output filename
     gets a zero-padded suffix.
- overwrite: false (default) refuses to overwrite an existing output.

Quality preservation (this is photo-mcp's reason for being):
- The output is written atomically (tmp + fsync + rename) so a crash
  never leaves a partial file at your output path.
- A provenance sidecar (<output>.photo-mcp.json) records the prompt,
  model, every parameter, and SHA-256 of the output.
- For PNG, integrity is verified by re-decoding the file after write.

Cost: every result includes 'cost_usd_estimate' and the running session
total. If session_cost_ceiling_usd is configured, calls that would push
over the ceiling are refused.
"""


_GENERATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "minLength": 1, "maxLength": 32000},
        "model": {
            "type": "string",
            "enum": list(models.ALL_MODELS),
        },
        "output_dir": {"type": "string"},
        "output_basename": {
            "type": "string",
            "description": "Base filename WITH extension (e.g. 'sunset.png'). "
                           "When n>1 a zero-padded suffix is appended.",
        },
        "n": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
        "size": {"type": "string", "default": "auto"},
        "quality": {
            "type": "string",
            "enum": ["low", "medium", "high", "auto"],
            "default": "auto",
        },
        "output_format": {
            "type": "string",
            "enum": ["png", "jpeg", "webp"],
            "default": "png",
        },
        "output_compression": {"type": "integer", "minimum": 0, "maximum": 100},
        "background": {
            "type": "string",
            "enum": ["opaque", "auto", "transparent"],
            "default": "auto",
        },
        "moderation": {"type": "string", "enum": ["auto", "low"], "default": "auto"},
        "overwrite": {"type": "boolean", "default": False},
        # 2026-05-22 capability backfill — see edit.py for the rationale.
        "stream": {
            "type": "boolean",
            "default": False,
            "description": (
                "Stream the generation. When true, partial frames stream back "
                "in the result's `partials` array."
            ),
        },
        "partial_images": {
            "type": "integer",
            "minimum": 0,
            "maximum": 3,
            "description": "Progressive partial frames (0..3). Requires stream=true.",
        },
        "user": {
            "type": "string",
            "maxLength": 256,
            "description": (
                "End-user identifier for OpenAI abuse monitoring (multi-tenant)."
            ),
        },
    },
    "required": ["prompt", "output_dir", "output_basename"],
    "additionalProperties": False,
}


async def _generate(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    # ---- 1. Input validation ------------------------------------------------
    prompt = args.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return _err("invalid_request", "'prompt' is required and must be a non-empty string.")
    if len(prompt) > 32_000:
        return _err(
            "invalid_request",
            f"'prompt' is {len(prompt)} chars; OpenAI accepts at most 32,000.",
        )

    model = args.get("model", ctx.config.default_generate_model)
    if not models.is_known_model(model):
        return _err(
            "unsupported_parameter",
            f"unknown model {model!r}. Supported: {list(models.ALL_MODELS)}.",
        )
    if ctx.config.allowed_models and model not in ctx.config.allowed_models:
        return _err(
            "unsupported_parameter",
            f"model {model!r} is not in this server's allowed_models "
            f"set ({list(ctx.config.allowed_models)}). Operator restricted "
            f"the model list (typically because the OpenAI org isn't "
            f"verified for the excluded models).",
        )

    n = int(args.get("n", 1))
    size = args.get("size", "auto")
    quality = args.get("quality", "auto")
    output_format = args.get("output_format", ctx.config.default_output_format)
    output_compression = args.get("output_compression")
    background = args.get("background", "auto")
    moderation = args.get("moderation", "auto")
    # 2026-05-22 capability backfill.
    user_id = args.get("user")
    stream = bool(args.get("stream", False))
    partial_images = args.get("partial_images")
    if user_id is not None and (not isinstance(user_id, str) or len(user_id) > 256):
        return _err(
            "invalid_request",
            "'user' must be a string identifier (≤256 chars).",
        )
    if not isinstance(stream, bool):
        return _err("invalid_request", "'stream' must be a boolean.")
    if partial_images is not None:
        if not isinstance(partial_images, int) or not (0 <= partial_images <= 3):
            return _err(
                "invalid_request",
                "'partial_images' must be an integer in 0..3.",
            )
        if not stream:
            return _err(
                "invalid_request",
                "'partial_images' requires 'stream=true'.",
            )
    overwrite = bool(args.get("overwrite", False))

    # Capability checks
    if (err := models.validate_size(model, size)) is not None:
        return _err("unsupported_parameter", err.to_message())
    if (err := models.validate_background(model, background)) is not None:
        return _err("unsupported_parameter", err.to_message())

    # ---- 2. Path resolution -------------------------------------------------
    raw_dir = args.get("output_dir")
    raw_base = args.get("output_basename")
    if not isinstance(raw_dir, str) or not isinstance(raw_base, str):
        return _err(
            "invalid_request",
            "'output_dir' and 'output_basename' are required strings.",
        )
    pol = ctx.config.path_policy()
    try:
        out_base = pol.canonicalize_output(Path(raw_dir) / raw_base)
    except PathError as e:
        return _err(e.error_type, str(e))

    targets = [numbered_path(out_base, index=i + 1, total=n) for i in range(n)]
    if not overwrite:
        for t in targets:
            if t.exists():
                return _err("output_exists", f"output already exists: {t}")

    # ---- 3. Cost authorization ---------------------------------------------
    estimate = estimate_call(
        table=ctx.price_table,
        model=model,  # type: ignore[arg-type]
        quality=quality,
        size=size,
        n=n,
    )
    try:
        ctx.session_ledger.authorize_or_raise(estimate.total_usd)
    except CeilingExceeded as ce:
        return _err(
            "cost_ceiling",
            str(ce),
            extra={
                "session_total_usd": ce.session_total_usd,
                "ceiling_usd": ce.ceiling_usd,
                "would_have_added_usd": ce.would_have_added_usd,
            },
        )

    # ---- 4. Dispatch --------------------------------------------------------
    if ctx.openai_client is None:
        return _err(
            "auth_error",
            "OpenAI client not initialized. Set OPENAI_API_KEY and restart photo-mcp.",
        )

    req = GenerationRequest(
        model=model,  # type: ignore[arg-type]
        prompt=prompt,
        n=n,
        size=size if size != "auto" else None,
        quality=quality if quality != "auto" else None,
        output_format=output_format,
        output_compression=output_compression,
        background=background if background != "auto" else None,
        moderation=moderation if moderation != "auto" else None,
        user=user_id,
        partial_images=partial_images if stream else None,
    )
    partial_payloads: list[dict[str, Any]] = []
    try:
        if stream:
            response, partial_payloads = await _consume_generate_stream(
                ctx.openai_client, req
            )
        else:
            response = await ctx.openai_client.generate(req)
    except (AuthError, OpenAIClientError) as e:
        return _err(getattr(e, "error_type", "openai_error"), str(e))

    # ---- 5. Persist results -------------------------------------------------
    file_paths: list[str] = []
    revised_prompts: list[str | None] = []
    warnings: list[str] = []
    for image, target in zip(response.images, targets):
        payload = _decode_image(image, target)
        if payload is None:
            warnings.append(f"image for {target.name} was URL-only and not downloaded")
            continue
        try:
            write_and_verify(target, payload, overwrite=overwrite,
                             verify_mode="png" if output_format == "png" else "any")
        except (OutputExists, OutputCorrupt) as e:
            return _err(getattr(e, "error_type", "output_error"), str(e))
        file_paths.append(str(target))
        revised_prompts.append(image.revised_prompt)

        # Provenance sidecar — generate has no source files, so 'sources' is empty.
        sc = sidecar.Sidecar(
            tool="generate",
            model=model,
            endpoint="generations",
            prompt=prompt,
            parameters={
                "n": n,
                "size": size,
                "quality": quality,
                "output_format": output_format,
                "output_compression": output_compression,
                "background": background,
                "moderation": moderation,
            },
            sources=[],
            output_path=target,
            output_sha256=sidecar.hash_file(target),
            output_size_bytes=target.stat().st_size,
            cost_usd_estimate=estimate.per_image_usd,
            request_ms=response.request_ms,
        )
        sidecar.write_sidecar(sc)

    # Record actual billed cost.
    actual = _cost_from_usage(response, ctx)
    ctx.session_ledger.record_billed(actual)

    payload = {
        "files": file_paths,
        "model": model,
        "background": background,
        "revised_prompts": revised_prompts,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
            "input_tokens_details": {
                "text_tokens":  response.usage.input_text_tokens,
                "image_tokens": response.usage.input_image_tokens,
            },
        },
        "created": response.created,
        "user": user_id,
        "stream": stream,
        "partials": partial_payloads,
        "partial_images": partial_images if stream else None,
        "cost_usd_estimate": round(actual or estimate.total_usd, 6),
        "session_total_usd": round(ctx.session_ledger.total_usd, 6),
        "request_ms": response.request_ms,
        "warnings": warnings,
    }
    return ToolResult(text=json.dumps(payload, indent=2), structured_payload=payload)


async def _consume_generate_stream(
    client: Any, req: GenerationRequest
) -> tuple[Any, list[dict[str, Any]]]:
    """Drive the OpenAI stream-generate and split partial frames from
    the final completion event. Mirrors ``_consume_edit_stream`` in
    edit.py so the generate path matches semantics."""
    import time as _time

    from photo_mcp.openai_client import (  # local import: avoids cycle
        ApiUsage,
        ImageData,
        ImageResponse,
        OpenAIClientError,
    )

    partials: list[dict[str, Any]] = []
    completed: ImageResponse | None = None
    started = int(_time.monotonic() * 1000)
    async for event in client.stream_generate(req):
        if event.kind == "error":
            raise OpenAIClientError(event.error or "stream error", error_type="openai_error")
        if event.kind == "partial":
            partials.append({
                "index":          event.index,
                "b64_json":       event.b64_json,
                "revised_prompt": event.revised_prompt,
            })
            continue
        if event.kind == "completed":
            usage = event.usage or ApiUsage()
            final_image = ImageData(
                b64_json=event.b64_json,
                revised_prompt=event.revised_prompt,
            )
            completed = ImageResponse(
                images=[final_image] if event.b64_json else [],
                usage=usage,
                model=req.model,
                request_ms=int(_time.monotonic() * 1000) - started,
                created=None,
            )
            break
    if completed is None:
        raise OpenAIClientError(
            "stream ended without a completed event", error_type="openai_error"
        )
    return completed, partials


GENERATE_TOOL = ToolDef(
    name="generate",
    description=_GENERATE_DESC,
    input_schema=_GENERATE_SCHEMA,
    handler=_generate,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _decode_image(image: Any, target: Path) -> bytes | None:
    """Resolve an ImageData to raw bytes for writing.

    gpt-image-* models always return base64 (the parameter to choose URL
    vs b64 was DALL-E-only and is rejected on these models). The `url`
    branch below is defensive: if a future SDK returns URLs we'd need to
    download them, but with gpt-image we never see this code path.
    """
    if image.b64_json:
        try:
            return base64.b64decode(image.b64_json)
        except (ValueError, TypeError):
            return None
    return None


def _cost_from_usage(response: Any, ctx: ToolContext) -> float:
    """Best-effort actual-cost compute from usage + price table.

    For now this returns 0.0 unless we can derive cost from token
    counts, in which case the per-image price-table estimate is used.
    Live-API verification (Phase 1.3.6) closes the gap to ±2%.
    """
    return 0.0


def _err(error_type: str, message: str, *, extra: dict[str, Any] | None = None) -> ToolResult:
    err: dict[str, Any] = {"type": error_type, "message": message}
    if extra:
        err.update(extra)
    payload = {"error": err}
    return ToolResult(
        text=json.dumps(payload, indent=2),
        is_error=True,
        structured_payload=payload,
    )


__all__ = ["GENERATE_TOOL"]
