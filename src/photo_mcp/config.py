"""Server configuration.

Resolution order (per system design §9):

    1. Built-in defaults
    2. TOML file at $XDG_CONFIG_HOME/photo-mcp/config.toml (Linux/Mac)
       or %APPDATA%\\photo-mcp\\config.toml (Windows)
    3. Environment variables (OPENAI_API_KEY, PHOTO_MCP_*)
    4. CLI flags (handled by main.py)
    5. Per-tool-call arguments (handled by tool input parsers)

Each later layer overrides the previous. ``OPENAI_API_KEY`` is the only
secret read; it is never logged in any form (NFR-3.2 + ``logging.redact``).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

if sys.version_info >= (3, 11):
    import tomllib as _toml  # type: ignore[import-not-found]
else:  # pragma: no cover — Python 3.12+ only project, kept for safety
    import tomli as _toml  # type: ignore[import-not-found]

from photo_mcp.paths import PathPolicy

# -----------------------------------------------------------------------------
# Default constants (per requirements doc + sponsor review guide §A defaults)
# -----------------------------------------------------------------------------

DEFAULT_GENERATE_MODEL: Final = "gpt-image-1.5"
DEFAULT_EDIT_MODEL: Final = "gpt-image-2"
DEFAULT_OUTPUT_FORMAT: Final = "png"
DEFAULT_QUALITY: Final = "auto"
DEFAULT_LOG_LEVEL: Final = "info"


# -----------------------------------------------------------------------------
# Errors
# -----------------------------------------------------------------------------


class ConfigError(Exception):
    """Raised on missing required config or malformed TOML."""


class MissingApiKey(ConfigError):
    """OPENAI_API_KEY env var is missing or empty."""


# -----------------------------------------------------------------------------
# Config record
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class Config:
    """Resolved server configuration.

    Mutable so :func:`load` can layer overrides cleanly. Once handed to
    the server it is treated as immutable in spirit (no mutation in tool
    handlers); per-call overrides go via the tool's input arguments
    rather than mutating Config.
    """

    # --- secrets ---------------------------------------------------------
    api_key: str = ""

    # --- model / call defaults ------------------------------------------
    default_generate_model: str = DEFAULT_GENERATE_MODEL
    default_edit_model: str = DEFAULT_EDIT_MODEL
    default_output_format: str = DEFAULT_OUTPUT_FORMAT
    default_quality: str = DEFAULT_QUALITY

    # --- cost controls ---------------------------------------------------
    # 0.0 means no ceiling (matches sponsor default per review guide §B.1).
    session_cost_ceiling_usd: float = 0.0

    # --- path policy -----------------------------------------------------
    allowed_input_roots: tuple[Path, ...] = ()
    allowed_output_roots: tuple[Path, ...] = ()
    follow_symlinks: bool = False

    # --- transport / logging -------------------------------------------
    log_level: str = DEFAULT_LOG_LEVEL
    transport: str = "stdio"  # "stdio" | "http"
    http_bind: str = "127.0.0.1:8765"

    # --- prices file -----------------------------------------------------
    # Default: bundled with the package; CLI / env can override for testing.
    prices_path: Path | None = None

    # ------------------------------------------------------------------
    # Convenience derivations
    # ------------------------------------------------------------------

    def path_policy(self) -> PathPolicy:
        return PathPolicy(
            allowed_input_roots=self.allowed_input_roots,
            allowed_output_roots=self.allowed_output_roots,
            follow_symlinks=self.follow_symlinks,
        )


# -----------------------------------------------------------------------------
# Loading
# -----------------------------------------------------------------------------


def _user_config_path() -> Path:
    """Per-user config file location, OS-aware.

    Linux/Mac: ``$XDG_CONFIG_HOME/photo-mcp/config.toml`` (defaults to
    ``~/.config/photo-mcp/config.toml`` if XDG var is unset).
    Windows: ``%APPDATA%\\photo-mcp\\config.toml``.
    Override via ``PHOTO_MCP_CONFIG`` env var.
    """
    override = os.environ.get("PHOTO_MCP_CONFIG")
    if override:
        return Path(override)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "photo-mcp" / "config.toml"
        return Path.home() / "AppData" / "Roaming" / "photo-mcp" / "config.toml"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "photo-mcp" / "config.toml"


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as f:
            return _toml.load(f)
    except FileNotFoundError:
        return {}
    except _toml.TOMLDecodeError as e:
        raise ConfigError(f"malformed TOML at {path}: {e}") from e


def _apply_toml(cfg: Config, data: dict[str, object]) -> Config:
    """Layer TOML values onto ``cfg``. Unknown keys are ignored (forward-compat)."""
    updates: dict[str, object] = {}
    if "default_generate_model" in data and isinstance(data["default_generate_model"], str):
        updates["default_generate_model"] = data["default_generate_model"]
    if "default_edit_model" in data and isinstance(data["default_edit_model"], str):
        updates["default_edit_model"] = data["default_edit_model"]
    if "default_output_format" in data and isinstance(data["default_output_format"], str):
        updates["default_output_format"] = data["default_output_format"]
    if "default_quality" in data and isinstance(data["default_quality"], str):
        updates["default_quality"] = data["default_quality"]
    if "session_cost_ceiling_usd" in data:
        try:
            updates["session_cost_ceiling_usd"] = float(data["session_cost_ceiling_usd"])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass  # silent ignore on bad type — env / CLI can correct
    if "log_level" in data and isinstance(data["log_level"], str):
        updates["log_level"] = data["log_level"]
    if "transport" in data and isinstance(data["transport"], str):
        updates["transport"] = data["transport"]
    if "http_bind" in data and isinstance(data["http_bind"], str):
        updates["http_bind"] = data["http_bind"]
    if "follow_symlinks" in data and isinstance(data["follow_symlinks"], bool):
        updates["follow_symlinks"] = data["follow_symlinks"]
    if "allowed_input_roots" in data and isinstance(data["allowed_input_roots"], list):
        updates["allowed_input_roots"] = tuple(
            Path(p).expanduser().resolve() for p in data["allowed_input_roots"] if isinstance(p, str)
        )
    if "allowed_output_roots" in data and isinstance(data["allowed_output_roots"], list):
        updates["allowed_output_roots"] = tuple(
            Path(p).expanduser().resolve() for p in data["allowed_output_roots"] if isinstance(p, str)
        )
    if "prices_path" in data and isinstance(data["prices_path"], str):
        updates["prices_path"] = Path(data["prices_path"]).expanduser().resolve()
    return replace(cfg, **updates) if updates else cfg


def _apply_env(cfg: Config) -> Config:
    """Layer environment-variable overrides onto ``cfg``.

    Reads:
      - OPENAI_API_KEY (required at server startup; absence is allowed
        here so tests can construct a Config without a key)
      - PHOTO_MCP_LOG_LEVEL
      - PHOTO_MCP_TRANSPORT
      - PHOTO_MCP_HTTP_BIND
      - PHOTO_MCP_COST_CEILING_USD
      - PHOTO_MCP_DEFAULT_GENERATE_MODEL
      - PHOTO_MCP_DEFAULT_EDIT_MODEL
      - PHOTO_MCP_DEFAULT_OUTPUT_FORMAT
      - PHOTO_MCP_DEFAULT_QUALITY
      - PHOTO_MCP_FOLLOW_SYMLINKS (true/false/1/0)
      - PHOTO_MCP_ALLOWED_INPUT_ROOTS  (path-separator-joined string;
        os.pathsep — ``:`` on POSIX, ``;`` on Windows)
      - PHOTO_MCP_ALLOWED_OUTPUT_ROOTS (same)
    """
    updates: dict[str, object] = {}
    if (key := os.environ.get("OPENAI_API_KEY", "").strip()):
        updates["api_key"] = key
    if (val := os.environ.get("PHOTO_MCP_LOG_LEVEL", "").strip()):
        updates["log_level"] = val.lower()
    if (val := os.environ.get("PHOTO_MCP_TRANSPORT", "").strip()):
        updates["transport"] = val.lower()
    if (val := os.environ.get("PHOTO_MCP_HTTP_BIND", "").strip()):
        updates["http_bind"] = val
    if (val := os.environ.get("PHOTO_MCP_COST_CEILING_USD", "").strip()):
        try:
            updates["session_cost_ceiling_usd"] = float(val)
        except ValueError:
            pass  # leave as configured; main.py validates
    for key_name, attr in (
        ("PHOTO_MCP_DEFAULT_GENERATE_MODEL", "default_generate_model"),
        ("PHOTO_MCP_DEFAULT_EDIT_MODEL", "default_edit_model"),
        ("PHOTO_MCP_DEFAULT_OUTPUT_FORMAT", "default_output_format"),
        ("PHOTO_MCP_DEFAULT_QUALITY", "default_quality"),
    ):
        if (val := os.environ.get(key_name, "").strip()):
            updates[attr] = val
    if (val := os.environ.get("PHOTO_MCP_FOLLOW_SYMLINKS", "").strip().lower()):
        if val in {"true", "1", "yes", "on"}:
            updates["follow_symlinks"] = True
        elif val in {"false", "0", "no", "off"}:
            updates["follow_symlinks"] = False
    if (val := os.environ.get("PHOTO_MCP_ALLOWED_INPUT_ROOTS", "").strip()):
        roots = tuple(
            Path(p).expanduser().resolve() for p in val.split(os.pathsep) if p
        )
        updates["allowed_input_roots"] = roots
    if (val := os.environ.get("PHOTO_MCP_ALLOWED_OUTPUT_ROOTS", "").strip()):
        roots = tuple(
            Path(p).expanduser().resolve() for p in val.split(os.pathsep) if p
        )
        updates["allowed_output_roots"] = roots
    return replace(cfg, **updates) if updates else cfg


def load(*, config_path: Path | None = None) -> Config:
    """Load configuration following the resolution order.

    ``config_path`` overrides the OS default location. Pass an explicit
    Path in tests to control which TOML (if any) is read.

    Does NOT raise on missing API key — that check is in
    :func:`require_api_key` so unit tests can build a Config without
    setting up an env.
    """
    cfg = Config()
    toml_path = config_path or _user_config_path()
    cfg = _apply_toml(cfg, _read_toml(toml_path))
    cfg = _apply_env(cfg)
    return cfg


def require_api_key(cfg: Config) -> str:
    """Return the API key or raise :class:`MissingApiKey`.

    Called at server startup (FR-8.2: fail-fast on missing key) and
    immediately before any OpenAI HTTP call as a defense-in-depth
    check. Returns the raw key — caller MUST NOT log it.
    """
    if not cfg.api_key:
        raise MissingApiKey(
            "OPENAI_API_KEY environment variable is not set or is empty. "
            "Set it before starting photo-mcp."
        )
    return cfg.api_key


__all__ = [
    "Config",
    "ConfigError",
    "DEFAULT_EDIT_MODEL",
    "DEFAULT_GENERATE_MODEL",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_OUTPUT_FORMAT",
    "DEFAULT_QUALITY",
    "MissingApiKey",
    "load",
    "require_api_key",
]
