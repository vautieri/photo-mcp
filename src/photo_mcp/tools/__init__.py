"""photo-mcp tools — one module per registered MCP tool.

Each module exposes:

- A ``ToolDef`` instance named after the tool (e.g. ``GENERATE_TOOL``)
- The async handler function
- The Pydantic input model (when applicable)

The ``register_all`` helper wires every tool into a ``PhotoMcpServer``
in one call from ``main.py``.
"""

from __future__ import annotations

from photo_mcp.server import PhotoMcpServer
from photo_mcp.tools.edit import EDIT_TOOL
from photo_mcp.tools.generate import GENERATE_TOOL
from photo_mcp.tools.info import ESTIMATE_COST_TOOL, LIST_MODELS_TOOL
from photo_mcp.tools.utility import ATTACH_METADATA_TOOL


def register_all(server: PhotoMcpServer) -> None:
    """Register every photo-mcp tool on ``server``."""
    server.register_tool(GENERATE_TOOL)
    server.register_tool(EDIT_TOOL)
    server.register_tool(LIST_MODELS_TOOL)
    server.register_tool(ESTIMATE_COST_TOOL)
    server.register_tool(ATTACH_METADATA_TOOL)


__all__ = [
    "ATTACH_METADATA_TOOL",
    "EDIT_TOOL",
    "ESTIMATE_COST_TOOL",
    "GENERATE_TOOL",
    "LIST_MODELS_TOOL",
    "register_all",
]
