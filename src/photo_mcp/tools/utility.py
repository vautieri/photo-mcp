"""``attach_metadata`` — copy EXIF/IPTC/XMP from one file to another.

Used internally by the edit/generate tools to re-attach source
metadata to outputs (FR-6.2). Exposed as its own tool so the
photographer can manually reattach metadata after some out-of-band
processing (e.g., color-correcting in Lightroom and wanting the
original camera tags preserved).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from photo_mcp import color, metadata
from photo_mcp.paths import PathError
from photo_mcp.server import ToolContext, ToolDef, ToolResult


_ATTACH_DESC = """\
Copy EXIF / IPTC / XMP metadata AND ICC color profile from a source
file to a target file. Used to reattach photographer-grade provenance
after an external transformation stripped it (Lightroom export,
external resizer, etc.). Both paths must already exist and live under
the configured allowed roots.

Accepted source formats: PNG, JPEG, WebP, GIF, TIFF, HEIC/HEIF (via
pillow-heif), and RAW (.cr2/.cr3/.nef/.arw/.dng/.raf/etc — read-only
on the metadata side; the binary is not re-encoded). Targets are
typically PNG/JPEG/WebP/TIFF — formats that can hold EXIF + ICC.

Inputs:
- source: path to the file holding the desired metadata + color profile
- target: path to the file that should receive them
- fields: optional list of field categories to copy. Valid:
    * 'exif' (camera/lens/exposure tags)
    * 'iptc' (caption/keywords/copyright)
    * 'xmp' (Adobe sidecar metadata, ratings, edits)
    * 'icc' (color profile — preserves AdobeRGB/ProPhoto/DisplayP3
            sources so the target renders identically; 2026-05-23
            addition. Without this, the target stays in whatever
            color space it was saved as, often sRGB-default which
            visibly shifts wedding/portrait skin tones.)
  Default: all four categories.

Returns: JSON with:
- source, target (canonicalized paths)
- copied: per-category booleans showing which were actually applied
- color_profile_name: identified profile name if 'icc' was requested
- warnings: aggregated list of non-fatal warnings
"""


_ATTACH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "description": "File whose metadata + ICC profile is the source of truth"},
        "target": {"type": "string", "description": "File that receives them"},
        "fields": {
            "type": "array",
            "items": {"type": "string", "enum": ["exif", "iptc", "xmp", "icc"]},
            "description": "Limit copy to these categories. Default: all four.",
        },
    },
    "required": ["source", "target"],
    "additionalProperties": False,
}


async def _attach_metadata(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    raw_source = args.get("source")
    raw_target = args.get("target")
    if not isinstance(raw_source, str) or not isinstance(raw_target, str):
        return _err("invalid_request", "Both 'source' and 'target' must be strings.")

    fields = args.get("fields") or ["exif", "iptc", "xmp", "icc"]
    if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
        return _err("invalid_request", "'fields' must be a list of strings.")

    pol = ctx.config.path_policy()
    try:
        source = pol.canonicalize_input(raw_source)
        # The target must also exist (we're appending metadata to it).
        target = pol.canonicalize_input(raw_target)
    except PathError as e:
        return _err(e.error_type, str(e))

    warnings: list[str] = []

    # ---- EXIF / IPTC / XMP ---------------------------------------------------
    snap = metadata.capture(source)
    if "exif" not in fields:
        snap.has_exif = False
    if "iptc" not in fields:
        snap.has_iptc = False
    if "xmp" not in fields:
        snap.has_xmp = False

    warnings.extend(snap.warnings)
    if any(f in fields for f in ("exif", "iptc", "xmp")):
        warnings.extend(metadata.reattach(snap, target))

    # ---- ICC ----------------------------------------------------------------
    # 2026-05-23 — standalone ICC reattach. Previously only callable
    # internally from edit.py via color.embed; surfacing here so a
    # photographer who exported through Lightroom (which sometimes
    # converts to sRGB without asking) can re-embed their AdobeRGB /
    # ProPhoto profile onto the round-tripped JPEG.
    color_profile_name: str | None = None
    if "icc" in fields:
        profile = color.capture(source)
        if profile is None:
            warnings.append(f"source {source} has no embedded ICC profile; skipped 'icc' field")
        else:
            color_profile_name = profile.identified_name
            try:
                color.embed(target, profile)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"failed to embed ICC profile onto {target}: {e}")

    payload = {
        "source": str(source),
        "target": str(target),
        "copied": {
            "exif": snap.has_exif and "exif" in fields,
            "iptc": snap.has_iptc and "iptc" in fields,
            "xmp":  snap.has_xmp  and "xmp"  in fields,
            "icc":  "icc" in fields and color_profile_name is not None,
        },
        "color_profile_name": color_profile_name,
        "warnings": warnings,
    }
    return ToolResult(text=json.dumps(payload, indent=2), structured_payload=payload)


ATTACH_METADATA_TOOL = ToolDef(
    name="attach_metadata",
    description=_ATTACH_DESC,
    input_schema=_ATTACH_SCHEMA,
    handler=_attach_metadata,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _err(error_type: str, message: str) -> ToolResult:
    payload = {"error": {"type": error_type, "message": message}}
    return ToolResult(
        text=json.dumps(payload, indent=2),
        is_error=True,
        structured_payload=payload,
    )


__all__ = ["ATTACH_METADATA_TOOL"]
