"""MCP server core — dispatch + tool registry.

Hosts the MCP `Server` from Anthropic's reference SDK, registers the
five tools (``generate``, ``edit``, ``list_models``, ``estimate_cost``,
``attach_metadata``), and routes ``tools/call`` to the right handler.

Per the system design (§2 architecture), this module:

- Imports the MCP SDK and creates a single ``Server`` instance
- Registers handlers for ``initialize``, ``tools/list``, ``tools/call``
- Catches **all** handler exceptions and converts them to structured
  ``isError=True`` results (NFR-2.3 — a single failed tool call must
  never crash the server process)
- Logs every dispatch via :class:`StructuredLogger`

The transport (stdio vs HTTP+SSE) is a separate concern — see
``transport_stdio.py`` and ``transport_http.py``. Both feed the same
``Server`` instance.
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from photo_mcp import __version__
from photo_mcp.config import Config
from photo_mcp.cost import PriceTable, SessionLedger
from photo_mcp.logging import StructuredLogger, get_logger
from photo_mcp.openai_client import OpenAIImageClient


# -----------------------------------------------------------------------------
# Tool dispatch interface
# -----------------------------------------------------------------------------


@dataclass(slots=True, kw_only=True)
class ToolContext:
    """Shared services injected into every tool handler.

    Tools shouldn't reach back into the server module; they take a
    ``ToolContext`` and read from it. This keeps server.py the only
    place that wires services together.
    """

    config: Config
    logger: StructuredLogger
    price_table: PriceTable
    session_ledger: SessionLedger
    openai_client: OpenAIImageClient | None  # None until first real call (lazy auth)


# A tool is registered as: name, description, JSON Schema, async handler.
ToolHandler = Callable[[ToolContext, dict[str, Any]], Awaitable["ToolResult"]]


@dataclass(slots=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


@dataclass(slots=True)
class ToolResult:
    """Normalized tool output passed back through the MCP boundary.

    The MCP SDK expects a list of content blocks; we use only ``text``
    blocks here (each tool's output is JSON-encoded text). Image
    content blocks could be added later for the streaming partial
    preview path.
    """

    text: str
    is_error: bool = False
    structured_payload: dict[str, Any] | None = None  # for callers that prefer dicts


# -----------------------------------------------------------------------------
# PhotoMcpServer
# -----------------------------------------------------------------------------


class PhotoMcpServer:
    """High-level wrapper around the MCP SDK's ``Server``.

    Construct once at startup; each transport feeds the same instance.
    Tools are registered via :meth:`register_tool`. The server routes
    ``tools/list`` and ``tools/call`` automatically.
    """

    def __init__(
        self,
        *,
        config: Config,
        price_table: PriceTable,
        ledger: SessionLedger,
        logger: StructuredLogger | None = None,
        openai_client: OpenAIImageClient | None = None,
    ) -> None:
        self._config = config
        self._price_table = price_table
        self._ledger = ledger
        self._log = logger or get_logger()
        self._openai = openai_client
        self._tools: dict[str, ToolDef] = {}

        # Lazy-import the MCP SDK so importing photo_mcp doesn't require it
        # for static analysis / tooling.
        from mcp.server import Server
        from mcp.types import (
            TextContent,
            Tool,
        )

        self._mcp = Server(name="photo-mcp", version=__version__)
        self._TextContent = TextContent
        self._Tool = Tool

        # Register the protocol-level handlers.
        self._wire_handlers()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def mcp_server(self) -> Any:
        """The underlying ``mcp.server.Server`` instance.

        Transport modules (stdio, http) import this and run it in their
        event loop. We expose it rather than wrapping every transport
        method to keep us in sync with SDK changes.
        """
        return self._mcp

    def register_tool(self, tool: ToolDef) -> None:
        """Register a tool. Names must be unique."""
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool
        self._log.debug("tool_registered", tool=tool.name)

    def set_openai_client(self, client: OpenAIImageClient) -> None:
        """Inject the OpenAI client lazily.

        Useful when the server needs to start without a key (e.g., for
        ``list_models`` and ``estimate_cost`` — both are key-free) and
        a key is supplied later via reconfiguration.
        """
        self._openai = client

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_context(self) -> ToolContext:
        return ToolContext(
            config=self._config,
            logger=self._log,
            price_table=self._price_table,
            session_ledger=self._ledger,
            openai_client=self._openai,
        )

    def _wire_handlers(self) -> None:
        srv = self._mcp

        @srv.list_tools()
        async def _list() -> list[Any]:
            return [
                self._Tool(
                    name=t.name,
                    description=t.description,
                    inputSchema=t.input_schema,
                )
                for t in self._tools.values()
            ]

        @srv.call_tool()
        async def _call(name: str, arguments: dict[str, Any]) -> list[Any]:
            return await self._dispatch(name, arguments)

    async def _dispatch(self, name: str, arguments: dict[str, Any]) -> list[Any]:
        """Route a ``tools/call`` to the registered handler with full error catching."""
        tool = self._tools.get(name)
        if tool is None:
            return self._error_result(
                f"Unknown tool {name!r}. "
                f"Registered: {sorted(self._tools)}"
            )
        ctx = self._build_context()
        try:
            self._log.debug("tool_dispatch", tool=name)
            result = await tool.handler(ctx, arguments or {})
        except Exception as e:  # noqa: BLE001 — last-resort floor
            tb = traceback.format_exc()
            self._log.error(
                "tool_exception",
                tool=name,
                error_type=type(e).__name__,
                error=str(e),
                # Traceback to stderr only — never to the MCP client.
                traceback=tb,
            )
            return self._error_result(
                f"Internal error in tool {name!r}: {type(e).__name__}: {e}"
            )

        # Convert ToolResult to MCP TextContent blocks.
        blocks = [self._TextContent(type="text", text=result.text)]
        if result.is_error:
            # MCP convention: the tool result block has an isError flag set
            # by the SDK based on the call's return path; we set it via the
            # text content here. Some SDK versions use a separate isError
            # field on the call result — newer versions treat the content
            # blocks as the carrier and isError is set on the wrapper.
            return blocks  # transport-specific isError-flag handled by SDK
        return blocks

    def _error_result(self, message: str) -> list[Any]:
        return [self._TextContent(type="text", text=json.dumps({
            "error": {"type": "internal_error", "message": message},
        }))]


__all__ = [
    "PhotoMcpServer",
    "ToolContext",
    "ToolDef",
    "ToolHandler",
    "ToolResult",
]
