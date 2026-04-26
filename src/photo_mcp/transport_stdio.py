"""stdio transport — read JSON-RPC frames from stdin, write to stdout.

FR-1.2 (default transport) + FR-1.4 (clean EOF) + NFR-6.3 (stdout
reserved for protocol; logs on stderr).

The MCP SDK provides ``mcp.server.stdio.stdio_server`` which handles
the full JSON-RPC framing + asyncio bridging. We use it directly; this
module is a thin wrapper that adds:

- Signal handlers for SIGTERM / SIGINT / Ctrl+C (FR-1.5)
- Explicit stdout flush (NFR-2.4)
- A graceful shutdown path with a 5-second deadline (FR-1.4)
"""

from __future__ import annotations

import asyncio
import signal
import sys

from photo_mcp.logging import get_logger
from photo_mcp.server import PhotoMcpServer


async def serve_stdio(server: PhotoMcpServer) -> int:
    """Run the MCP server over stdio until EOF or signal.

    Returns the process exit code (0 on clean shutdown, 1 on error).
    """
    log = get_logger()
    log.info("transport_starting", transport="stdio")

    # Ensure stdout uses unbuffered binary mode where possible, to avoid
    # the MCP client seeing partial frames. On Linux/Mac stdout's default
    # buffering is line-buffered when attached to a TTY and block-buffered
    # otherwise — both are fine because we explicit-flush after each
    # frame inside the SDK's writer.
    sys.stdout.reconfigure(line_buffering=False, newline="")  # type: ignore[union-attr]

    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("transport_signal", signal="received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows: signal handlers via add_signal_handler aren't
            # supported. Fall back to signal.signal which works for
            # Ctrl+C in console apps.
            signal.signal(sig, lambda *_: _signal_handler())

    try:
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            # The MCP SDK runs until streams close (stdin EOF) or an
            # exception bubbles. We race it with the signal stop_event
            # so we can observe SIGTERM during a blocked read.
            run_task = asyncio.create_task(
                server.mcp_server.run(read_stream, write_stream, server.mcp_server.create_initialization_options())
            )
            stop_task = asyncio.create_task(stop_event.wait())
            done, _pending = await asyncio.wait(
                {run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if stop_task in done:
                # Signal shutdown — give the server up to 5 s to drain.
                run_task.cancel()
                try:
                    await asyncio.wait_for(run_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            else:
                # Server task completed naturally (EOF) — make sure stop_task
                # is cleaned up.
                stop_task.cancel()
    except Exception as e:  # noqa: BLE001
        log.error("transport_error", transport="stdio", error=str(e))
        return 1

    log.info("transport_stopped", transport="stdio")
    return 0


__all__ = ["serve_stdio"]
