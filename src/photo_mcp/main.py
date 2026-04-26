"""Entry point — wire config, services, server, transport, and tools.

Invoked via ``python -m photo_mcp`` or the ``photo-mcp`` console script.
Returns the process exit code; the actual server loop runs inside the
selected transport (stdio default, HTTP+SSE optional).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from photo_mcp import __version__
from photo_mcp.config import Config, MissingApiKey, load, require_api_key
from photo_mcp.cost import PricingError, SessionLedger, load_default, load_from_path
from photo_mcp.logging import get_logger
from photo_mcp.openai_client import OpenAIImageClient
from photo_mcp.retry import RetryPolicy
from photo_mcp.server import PhotoMcpServer
from photo_mcp.tools import register_all
from photo_mcp.transport_stdio import serve_stdio


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="photo-mcp",
        description="MCP server for OpenAI gpt-image with photographer-grade quality preservation",
    )
    parser.add_argument("--version", action="version", version=f"photo-mcp {__version__}")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default=None,
        help="Transport mode (overrides config; defaults to stdio)",
    )
    parser.add_argument(
        "--http-bind",
        default=None,
        help="HTTP+SSE bind address (only used with --transport http)",
    )
    parser.add_argument(
        "--log-level",
        choices=("debug", "info", "warning", "error"),
        default=None,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a TOML config file (overrides default location)",
    )
    parser.add_argument(
        "--prices",
        type=Path,
        default=None,
        help="Path to a custom prices.json (defaults to bundled)",
    )
    parser.add_argument(
        "--allowed-input-roots",
        default=None,
        help=f"OS-pathsep-joined list of allowed input directories",
    )
    parser.add_argument(
        "--allowed-output-roots",
        default=None,
        help=f"OS-pathsep-joined list of allowed output directories",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Permit symlink components in input/output paths (default: refuse)",
    )
    return parser.parse_args(argv)


def _apply_cli_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    """Layer CLI overrides on top of the env+TOML config."""
    from dataclasses import replace
    updates: dict[str, object] = {}
    if args.transport:
        updates["transport"] = args.transport
    if args.http_bind:
        updates["http_bind"] = args.http_bind
    if args.log_level:
        updates["log_level"] = args.log_level
    if args.allowed_input_roots:
        updates["allowed_input_roots"] = tuple(
            Path(p).expanduser().resolve()
            for p in args.allowed_input_roots.split(os.pathsep)
            if p
        )
    if args.allowed_output_roots:
        updates["allowed_output_roots"] = tuple(
            Path(p).expanduser().resolve()
            for p in args.allowed_output_roots.split(os.pathsep)
            if p
        )
    if args.follow_symlinks:
        updates["follow_symlinks"] = True
    if args.prices:
        updates["prices_path"] = args.prices
    return replace(cfg, **updates) if updates else cfg


async def _run(args: argparse.Namespace) -> int:
    log = get_logger()

    # ---- 1. Config + secrets ---------------------------------------------
    cfg = load(config_path=args.config)
    cfg = _apply_cli_overrides(cfg, args)
    log.set_level(cfg.log_level)  # type: ignore[arg-type]

    # API key is OPTIONAL at startup. Without one, list_models / estimate_cost
    # / attach_metadata still work (they don't touch the API); generate / edit
    # return a structured auth_error to the caller. This lets a parent agent
    # introspect the server's capabilities without provisioning a key first.
    api_key = cfg.api_key
    if not api_key:
        log.warning(
            "startup_no_api_key",
            message="OPENAI_API_KEY not set — generate/edit will refuse calls "
                    "until a key is provided. Read-only tools work normally.",
        )

    # ---- 2. Price table ---------------------------------------------------
    try:
        price_table = (
            load_from_path(cfg.prices_path) if cfg.prices_path else load_default()
        )
    except PricingError as e:
        log.error("startup_failed", reason="bad_prices", message=str(e))
        sys.stderr.write(f"{e}\n")
        return 3

    # ---- 3. Services ------------------------------------------------------
    ledger = SessionLedger(ceiling_usd=cfg.session_cost_ceiling_usd)
    client: OpenAIImageClient | None = None
    if api_key:
        client = OpenAIImageClient(
            api_key=api_key,
            retry_policy=RetryPolicy(),
            logger=log,
        )

    # ---- 4. MCP server + tools -------------------------------------------
    server = PhotoMcpServer(
        config=cfg,
        price_table=price_table,
        ledger=ledger,
        logger=log,
        openai_client=client,
    )
    register_all(server)

    # ---- 5. Transport ----------------------------------------------------
    log.info(
        "server_starting",
        version=__version__,
        transport=cfg.transport,
        cost_ceiling_usd=cfg.session_cost_ceiling_usd,
        api_key_prefix=(
            (api_key[:4] + "...") if (api_key and len(api_key) > 4) else "(none)"
        ),
        openai_client_ready=client is not None,
    )
    if cfg.transport == "stdio":
        return await serve_stdio(server)
    if cfg.transport == "http":
        # Lazy import — the http extras may not be installed.
        try:
            from photo_mcp.transport_http import serve_http
        except ImportError:
            sys.stderr.write(
                "HTTP transport requires the 'http' extras: "
                "pip install 'photo-mcp[http]'\n"
            )
            return 4
        return await serve_http(server, bind=cfg.http_bind)
    sys.stderr.write(f"Unknown transport: {cfg.transport!r}\n")
    return 5


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001
        # Last-resort floor — should never fire (server.py catches per-tool;
        # transport catches per-frame). If it does, log loud and exit 1.
        get_logger().error(
            "fatal_uncaught", error_type=type(e).__name__, error=str(e)
        )
        sys.stderr.write(f"FATAL: {type(e).__name__}: {e}\n")
        return 1


__all__ = ["main"]
