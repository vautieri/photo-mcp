"""Provenance sidecar — writes ``<output>.photo-mcp.json`` for every result.

Implements QR-10..12 from the requirements doc. The sidecar is the
sponsor's authenticity guarantee: every output ships with a JSON file
that records each source's path + SHA-256, the prompt, the model, every
parameter, the SSIM score, and the cost. Years later the photographer
can hand over the sidecar plus the source files and prove the lineage
by re-hashing.

Schema is documented in ``docs/05-system-design.md`` §5.3. Forward
compatibility: future minor versions add fields; readers ignore
unknown keys.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from photo_mcp import __version__ as _photo_mcp_version

SIDECAR_SCHEMA_URL = "https://photo-mcp.example/schemas/sidecar/v0.1.0"
SIDECAR_VERSION = "0.1.0"
SIDECAR_SUFFIX = ".photo-mcp.json"

# How much of a source file to read at a time when computing SHA-256.
# 1 MB chunks balance throughput and memory for large RAW files (≤ 50 MB).
_HASH_CHUNK = 1 * 1024 * 1024


# -----------------------------------------------------------------------------
# Source descriptor
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceRef:
    """One source file referenced by a tool call.

    The provenance sidecar lists every input image (and the mask, if any)
    as a SourceRef. SHA-256 is computed from the file ON DISK at the
    moment the call ran — not from any in-memory representation that
    might have been re-encoded.
    """

    path: Path
    sha256: str
    size_bytes: int
    mime: str

    @classmethod
    def from_file(cls, path: Path) -> SourceRef:
        return cls(
            path=path,
            sha256=_hash_file(path),
            size_bytes=path.stat().st_size,
            mime=_mime_for(path),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mime": self.mime,
        }


# -----------------------------------------------------------------------------
# Sidecar record
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class Sidecar:
    """Full sidecar payload — written next to every output file."""

    tool: str
    model: str
    endpoint: str
    prompt: str
    parameters: dict[str, Any]
    sources: list[SourceRef]
    output_path: Path
    output_sha256: str
    output_size_bytes: int
    cost_usd_estimate: float
    request_ms: int
    mask: SourceRef | None = None
    ssim_to_image_0: float | None = None
    metadata_preserved_from: Path | None = None
    color_profile_preserved_from: Path | None = None
    color_profile_name: str | None = None
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""  # filled by build_default if empty
    photo_mcp_version: str = _photo_mcp_version
    schema: str = SIDECAR_SCHEMA_URL
    version: str = SIDECAR_VERSION

    def to_dict(self) -> dict[str, Any]:
        if not self.created_at:
            self.created_at = _utc_now_iso()
        d: dict[str, Any] = {
            "$schema": self.schema,
            "version": self.version,
            "photo_mcp_version": self.photo_mcp_version,
            "created_at": self.created_at,
            "tool": self.tool,
            "model": self.model,
            "endpoint": self.endpoint,
            "prompt": self.prompt,
            "parameters": self.parameters,
            "sources": [s.to_dict() for s in self.sources],
            "mask": self.mask.to_dict() if self.mask else None,
            "output": {
                "path": str(self.output_path),
                "sha256": self.output_sha256,
                "size_bytes": self.output_size_bytes,
            },
            "ssim_to_image_0": self.ssim_to_image_0,
            "metadata_preserved_from": (
                str(self.metadata_preserved_from)
                if self.metadata_preserved_from is not None
                else None
            ),
            "color_profile_preserved_from": (
                str(self.color_profile_preserved_from)
                if self.color_profile_preserved_from is not None
                else None
            ),
            "color_profile_name": self.color_profile_name,
            "warnings": list(self.warnings),
            "cost_usd_estimate": self.cost_usd_estimate,
            "request_ms": self.request_ms,
        }
        return d


# -----------------------------------------------------------------------------
# Builder + writer
# -----------------------------------------------------------------------------


def sidecar_path_for(output_path: Path) -> Path:
    """Return the sibling sidecar path: ``<output>.photo-mcp.json``."""
    return output_path.with_name(output_path.name + SIDECAR_SUFFIX)


def write_sidecar(sidecar: Sidecar, *, atomic: bool = True) -> Path:
    """Serialize and write the sidecar to disk.

    QR-11 atomicity: temp file + fsync + rename. If the rename fails we
    leave nothing behind. The output file MUST already exist on disk
    (this function does not validate that — the writer does).

    Returns the resolved sidecar path.
    """
    target = sidecar_path_for(sidecar.output_path)
    payload = json.dumps(sidecar.to_dict(), indent=2, ensure_ascii=False, default=_default)
    if not atomic:
        target.write_text(payload, encoding="utf-8")
        return target

    # Atomic write: create temp file in the same directory (so rename is
    # an inode swap, not a cross-device copy), fsync, then rename.
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=target.name + ".",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
    return target


# -----------------------------------------------------------------------------
# Hashing
# -----------------------------------------------------------------------------


def hash_file(path: Path) -> str:
    """SHA-256 of a file. Public helper; mirrors the hashing the builder uses."""
    return _hash_file(path)


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _mime_for(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return str(obj)


__all__ = [
    "SIDECAR_SCHEMA_URL",
    "SIDECAR_SUFFIX",
    "SIDECAR_VERSION",
    "Sidecar",
    "SourceRef",
    "hash_bytes",
    "hash_file",
    "sidecar_path_for",
    "write_sidecar",
]
