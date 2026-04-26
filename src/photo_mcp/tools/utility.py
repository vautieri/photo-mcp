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

from photo_mcp import metadata
from photo_mcp.paths import PathError
from photo_mcp.server import ToolContext, ToolDef, ToolResult


_ATTACH_DESC = """\
Copy EXIF / IPTC / XMP metadata from a source file to a target file.
Used to reattach photographer metadata after an external transformation
that stripped it. Both paths must already exist and be under the
configured allowed roots.

Inputs:
- source: path to the file holding the desired metadata
- target: path to the file that should receive the metadata
- fields: optional list of field categories to limit the copy to.
          Valid: 'exif', 'iptc', 'xmp'. Default: all three.

Returns: JSON with:
- source, target (canonicalized paths)
- copied: object showing which categories were copied (and any per-category warnings)
- warnings: aggregated list of non-fatal warnings
"""


_ATTACH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "description": "File whose metadata is the source of truth"},
        "target": {"type": "string", "description": "File that receives the metadata"},
        "fields": {
            "type": "array",
            "items": {"type": "string", "enum": ["exif", "iptc", "xmp"]},
            "description": "Limit copy to these categories. Default: all three.",
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

    fields = args.get("fields") or ["exif", "iptc", "xmp"]
    if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
        return _err("invalid_request", "'fields' must be a list of strings.")

    pol = ctx.config.path_policy()
    try:
        source = pol.canonicalize_input(raw_source)
        # The target must also exist (we're appending metadata to it).
        target = pol.canonicalize_input(raw_target)
    except PathError as e:
        return _err(e.error_type, str(e))

    snap = metadata.capture(source)
    # Filter the snapshot per requested fields.
    if "exif" not in fields:
        snap.has_exif = False
    if "iptc" not in fields:
        snap.has_iptc = False
    if "xmp" not in fields:
        snap.has_xmp = False

    warnings = list(snap.warnings)
    warnings.extend(metadata.reattach(snap, target))

    payload = {
        "source": str(source),
        "target": str(target),
        "copied": {
            "exif": snap.has_exif and "exif" in fields,
            "iptc": snap.has_iptc and "iptc" in fields,
            "xmp": snap.has_xmp and "xmp" in fields,
        },
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
