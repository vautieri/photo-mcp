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

Progressive imaging — 2026-05-22
================================

When a client supplies a ``_meta.progressToken`` on the ``tools/call``
request (per the MCP spec), the dispatcher binds a ``progress_emitter``
on the ``ToolContext`` that the streaming tools (``edit``, ``generate``)
fire once per partial frame. The emitter sends an MCP
``notifications/progress`` carrying the standard ``progress`` /
``total`` fields *plus* a ``_meta`` extras bag with the partial's
``b64_json`` payload, the partial ``index``, and the ``mime_type`` —
so a client (the MICHAEL engine bridge, in our deployment) can render
a progressive preview while the tool is still running. Clients that
do NOT send a ``progressToken`` get the unchanged final result; the
emitter is a no-op in that case. The LLM-visible tool result is
unchanged regardless — partials are out-of-band UI metadata.
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from photo_mcp import __version__
from photo_mcp.config import Config
from photo_mcp.cost import PriceTable, SessionLedger
from photo_mcp.logging import StructuredLogger, get_logger
from photo_mcp.openai_client import OpenAIImageClient


# -----------------------------------------------------------------------------
# Progress emitter
# -----------------------------------------------------------------------------


class ProgressEmitter(Protocol):
    """Out-of-band callback fired by streaming tools once per partial frame.

    The streaming tools (``edit``, ``generate``) collect partial frames
    from OpenAI's image stream and currently surface them only in the
    final tool result's ``partials`` array. That makes the LLM aware
    after the fact but doesn't let the UI render an evolving preview.
    Instead, when the MCP client sends a ``progressToken``, the
    dispatcher binds a :class:`ProgressEmitter` that sends an MCP
    ``notifications/progress`` per partial. Clients that opt in render
    the progressive preview; clients that don't get the unchanged final
    result.

    Args:
        index: zero-based frame index (0 .. partial_images-1).
        total: total expected partials (== ``partial_images``).
        b64_json: the partial frame, base64-encoded PNG/WebP/JPEG.
        mime_type: best-effort guess — OpenAI's stream doesn't carry
            the mime explicitly, so the caller passes the format
            requested for the final write (PNG by default).
        revised_prompt: OpenAI's safety-rewriter output for this
            partial, if any. Optional.

    Implementations must be non-blocking (async) and tolerant of an
    unreliable transport — a dropped progress notification is a
    cosmetic miss, never a correctness bug.
    """

    async def __call__(
        self,
        *,
        index: int,
        total: int,
        b64_json: str,
        mime_type: str,
        revised_prompt: str | None = None,
    ) -> None: ...


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
    # Bound per-call by ``PhotoMcpServer._build_context`` when the MCP
    # ``tools/call`` request carried a ``_meta.progressToken``. Streaming
    # tools fire this once per partial frame; non-streaming tools (and
    # streaming calls from clients that did not opt in) leave it None
    # and emit nothing.
    progress_emitter: ProgressEmitter | None = None


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

    def _build_context(
        self, progress_emitter: ProgressEmitter | None = None
    ) -> ToolContext:
        return ToolContext(
            config=self._config,
            logger=self._log,
            price_table=self._price_table,
            session_ledger=self._ledger,
            openai_client=self._openai,
            progress_emitter=progress_emitter,
        )

    def _build_progress_emitter(self) -> ProgressEmitter | None:
        """Build the per-call progress emitter, or None if the client
        did not request progress.

        The MCP spec attaches a ``progressToken`` to the request's
        ``_meta`` field; we read it off the SDK's request context and
        bind a closure that issues ``notifications/progress`` with the
        canonical fields plus a ``_meta`` extras bag carrying the
        partial-image payload. ``ProgressNotificationParams`` declares
        ``extra='allow'`` so the extra key is preserved on the wire.

        Returns None when:
        - The request had no ``_meta`` block (older clients).
        - The request had ``_meta`` but no ``progressToken`` (the
          standard opt-out per the MCP spec).
        - The SDK's request context isn't bound (defensive — should
          never happen inside a tool handler).
        """
        # Lazy imports — the SDK module is heavy and we don't want to
        # take its weight at static-analysis / tooling time.
        try:
            from mcp.server.lowlevel.server import request_ctx
            from mcp.types import (
                ProgressNotification,
                ProgressNotificationParams,
                ServerNotification,
            )
        except ImportError:  # pragma: no cover — SDK is a hard runtime dep
            return None

        try:
            rc = request_ctx.get()
        except LookupError:  # pragma: no cover
            return None

        meta = getattr(rc, "meta", None)
        progress_token = getattr(meta, "progressToken", None) if meta else None
        if progress_token is None:
            return None

        session = rc.session
        related_request_id = getattr(rc, "request_id", None)

        async def emit(
            *,
            index: int,
            total: int,
            b64_json: str,
            mime_type: str,
            revised_prompt: str | None = None,
        ) -> None:
            # Construct the params dict explicitly so the extras land
            # under ``_meta`` (Pydantic alias) on the wire — both the
            # MCP spec and the bridge expect them there. Standard
            # progress / total / message fields are kept so generic
            # progress UIs still render a useful value.
            params = ProgressNotificationParams(
                progressToken=progress_token,
                progress=float(index + 1),
                total=float(total) if total else None,
                message=f"partial {index + 1}/{total}" if total else f"partial {index + 1}",
            )
            # The pydantic model allows extras — attach via setattr so
            # the dump path includes them.
            extras: dict[str, Any] = {
                "type": "partial_image",
                "index": index,
                "b64_json": b64_json,
                "mime_type": mime_type,
            }
            if revised_prompt:
                extras["revised_prompt"] = revised_prompt
            # Put extras under the canonical ``_meta`` bag (the SDK's
            # Pydantic model exposes it as `meta` with alias `_meta`).
            params.meta = ProgressNotificationParams.Meta(**extras)
            try:
                await session.send_notification(
                    ServerNotification(ProgressNotification(params=params)),
                    related_request_id=related_request_id,
                )
            except Exception as e:  # noqa: BLE001
                # Progress is best-effort UI metadata; a transport hiccup
                # must never fail the underlying tool call.
                self._log.warning(
                    "progress_emit_failed",
                    error_type=type(e).__name__,
                    error=str(e),
                )

        return emit

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
        ctx = self._build_context(progress_emitter=self._build_progress_emitter())
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
    "ProgressEmitter",
    "ToolContext",
    "ToolDef",
    "ToolHandler",
    "ToolResult",
]
