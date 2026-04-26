"""photo-mcp — MCP server for OpenAI gpt-image with photographer-grade quality preservation.

Public surface is intentionally small. Tools and transports are wired in
``photo_mcp.main``; consumers should import from this package only for
the version constant and the supported model identifiers.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Re-export the model identifiers so external code (e.g. tests, downstream
# tools) can reference them by name without importing from the implementation
# module. The capability matrix lives in ``photo_mcp.models``.
from photo_mcp.models import ModelId  # noqa: E402

__all__ = ["__version__", "ModelId"]
