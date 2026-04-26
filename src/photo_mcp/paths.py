"""Filesystem path safety.

Per NFR-3.3..3.7: input and output paths from MCP clients are canonicalized
and rejected if they traverse outside the configured allow-list, refuse to
follow symlinks unless explicitly enabled, and never accept device paths
that could read kernel state (``/dev``, ``/proc``, etc.).

The allow-list is a configuration concern — :class:`PathPolicy` accepts
the lists at construction time so the caller (``config.py``) can supply
them from env / CLI / TOML.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Device paths that must never be read or written even if the allow-list
# would otherwise permit them. Matches the device-path block list in
# MICHAEL's safety_and_isolation.hpp; same threat model.
_BLOCKED_DEVICE_PREFIXES: tuple[str, ...] = (
    "/dev/",
    "/proc/",
    "/sys/",
)


class PathError(Exception):
    """Base class for path-policy violations.

    Subclasses are mapped to ER-* error envelopes by the dispatch layer
    (see ER-1 / NFR-3.3 in requirements doc).
    """

    error_type: str = "path_error"

    def to_dict(self) -> dict[str, str]:
        return {"type": self.error_type, "message": str(self)}


class PathOutsideRoots(PathError):
    error_type = "path_outside_roots"


class PathIsSymlink(PathError):
    error_type = "path_is_symlink"


class PathBlockedDevice(PathError):
    error_type = "path_blocked_device"


class PathDoesNotExist(PathError):
    error_type = "path_does_not_exist"


@dataclass(frozen=True, slots=True)
class PathPolicy:
    """Configurable path-safety policy.

    Attributes:
        allowed_input_roots: directories under which input files may live.
            Empty means ``Path.home()`` is the sole allowed root.
        allowed_output_roots: directories under which outputs may be written.
            Empty means ``Path.home()`` is the sole allowed root.
        follow_symlinks: when False (default), any path component that is
            a symlink causes rejection. When True, the resolved target
            must still be under an allowed root.
    """

    allowed_input_roots: tuple[Path, ...] = ()
    allowed_output_roots: tuple[Path, ...] = ()
    follow_symlinks: bool = False

    def _input_roots(self) -> tuple[Path, ...]:
        return self.allowed_input_roots or (Path.home().resolve(),)

    def _output_roots(self) -> tuple[Path, ...]:
        return self.allowed_output_roots or (Path.home().resolve(),)

    # ------------------------------------------------------------------
    # Input paths (must exist; will be read)
    # ------------------------------------------------------------------

    def canonicalize_input(self, raw: str | Path) -> Path:
        """Resolve and validate an input path.

        Returns the canonical path on success. Raises PathError on any
        violation. The returned path is suitable for ``open(..., "rb")``.
        """
        # Reject empty BEFORE constructing a Path — Path("") becomes Path(".")
        # which would canonicalize to the CWD and pass into the allow-list
        # check, producing a misleading PathOutsideRoots instead of the
        # PathDoesNotExist we actually want.
        if isinstance(raw, str) and not raw.strip():
            raise PathDoesNotExist("empty path supplied")
        p = Path(raw)
        try:
            resolved = p.resolve(strict=True)
        except (FileNotFoundError, OSError) as e:
            raise PathDoesNotExist(f"input does not exist: {p}") from e
        self._reject_blocked_device(resolved)
        if not self.follow_symlinks:
            self._reject_symlink(p)
        self._enforce_under_roots(resolved, self._input_roots(), "input")
        return resolved

    # ------------------------------------------------------------------
    # Output paths (may not exist yet; will be written)
    # ------------------------------------------------------------------

    def canonicalize_output(self, raw: str | Path) -> Path:
        """Resolve and validate an output path.

        Returns the canonical path. Parent directory must exist or be
        creatable under an allowed output root. Caller is responsible
        for collision checks (FR-5.3).
        """
        if isinstance(raw, str) and not raw.strip():
            raise PathDoesNotExist("empty output path supplied")
        p = Path(raw)
        # Output may not exist yet. Resolve the parent strictly; combine
        # with the leaf manually so we can validate the would-be path.
        parent = p.parent if p.parent != Path("") else Path.cwd()
        try:
            resolved_parent = parent.resolve(strict=True)
        except (FileNotFoundError, OSError) as e:
            raise PathDoesNotExist(
                f"output parent directory does not exist: {parent}"
            ) from e
        resolved = resolved_parent / p.name
        self._reject_blocked_device(resolved)
        # Check the parent isn't a symlink (when symlinks are forbidden);
        # the leaf may not exist so we can't query its symlink state yet.
        if not self.follow_symlinks:
            self._reject_symlink(parent)
        self._enforce_under_roots(resolved, self._output_roots(), "output")
        return resolved

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _reject_blocked_device(p: Path) -> None:
        s = str(p).replace("\\", "/")
        for prefix in _BLOCKED_DEVICE_PREFIXES:
            if s.startswith(prefix) or s == prefix.rstrip("/"):
                raise PathBlockedDevice(
                    f"device path is not permitted as a tool input/output: {p}"
                )

    @staticmethod
    def _reject_symlink(p: Path) -> None:
        # Walk the path and refuse if any component on disk is a symlink.
        # Path.is_symlink() only tests the leaf; we want any-component test.
        cur = Path(p.anchor) if p.anchor else Path.cwd()
        try:
            parts = p.relative_to(p.anchor).parts if p.anchor else p.parts
        except ValueError:
            parts = p.parts
        for name in parts:
            cur = cur / name
            try:
                if cur.is_symlink():
                    raise PathIsSymlink(
                        f"path component {cur} is a symlink; "
                        "set follow_symlinks=true to permit"
                    )
            except OSError:
                # Component might not exist (output case). Stop walking;
                # canonicalize_output handles non-existent leaves.
                break

    @staticmethod
    def _enforce_under_roots(p: Path, roots: tuple[Path, ...], label: str) -> None:
        for root in roots:
            try:
                p.relative_to(root)
                return
            except ValueError:
                continue
        raise PathOutsideRoots(
            f"{label} path {p} is outside the allowed roots: "
            + ", ".join(str(r) for r in roots)
        )


# Convenience for tests / callers that want process-default policy without
# threading a config through. NOT used in production dispatch — server.py
# reads config and constructs a PathPolicy explicitly.
def default_policy() -> PathPolicy:
    return PathPolicy(
        allowed_input_roots=(Path.home().resolve(),),
        allowed_output_roots=(Path.home().resolve(),),
        follow_symlinks=False,
    )


__all__ = [
    "PathBlockedDevice",
    "PathDoesNotExist",
    "PathError",
    "PathIsSymlink",
    "PathOutsideRoots",
    "PathPolicy",
    "default_policy",
]
