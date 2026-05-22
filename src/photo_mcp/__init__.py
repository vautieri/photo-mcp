"""photo-mcp — MCP server for OpenAI gpt-image with photographer-grade quality preservation.

Public surface is intentionally small. Tools and transports are wired in
``photo_mcp.main``; consumers should import from this package only for
the version constant and the supported model identifiers.
"""

from __future__ import annotations

__version__ = "0.1.0"

# 2026-05-22 — register pillow-heif with Pillow so every Image.open()
# across the codebase (metadata.py, color.py, output.py, raw.py,
# tools/edit.py) transparently accepts HEIC/HEIF as if it were a
# native PIL format. Without this, every iPhone .heic input failed
# the format probe and the LLM was forced to pre-transcode (wasted
# turn, lossy result, the photographer's exact complaint).
#
# Registration is a no-op if pillow-heif isn't installed (it's
# pinned in pyproject.toml so the prod install always has it; the
# try-except is for dev environments mid-`pip install`).
try:
    import pillow_heif as _pillow_heif

    _pillow_heif.register_heif_opener()
except ImportError:
    # pillow-heif is a runtime dep but not strictly required for
    # PNG/JPEG/WebP/RAW flows; degrade gracefully.
    pass

# Re-export the model identifiers so external code (e.g. tests, downstream
# tools) can reference them by name without importing from the implementation
# module. The capability matrix lives in ``photo_mcp.models``.
from photo_mcp.models import ModelId  # noqa: E402

__all__ = ["__version__", "ModelId"]
