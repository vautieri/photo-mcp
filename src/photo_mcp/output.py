"""Atomic output writing + integrity verification.

FR-5.2..5.4 + FR-6.7 + IR-3.2 — outputs are written via tmp+fsync+rename
so a crash mid-write never leaves a half-image at the target path. Each
written PNG is re-decoded after the rename to verify byte integrity
(``Image.verify()``); failure unlinks the file and raises so the user
never sees a corrupt result mistaken for a clean one.

For ``n>1`` calls, the server appends a zero-padded numeric suffix to
the user-supplied basename (``-001``, ``-002``, ...). The width of the
padding matches the number of digits in ``n`` (so ``n=10`` produces
``-01`` … ``-10``).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class OutputError(Exception):
    error_type: str = "output_error"


class OutputExists(OutputError):
    error_type = "output_exists"


class OutputCorrupt(OutputError):
    error_type = "output_corrupt"


# -----------------------------------------------------------------------------
# Suffix generation for n > 1
# -----------------------------------------------------------------------------


def numbered_path(base: Path, *, index: int, total: int) -> Path:
    """Return ``base`` with a zero-padded suffix appropriate for ``total``.

    Examples:
        numbered_path(Path("a/b/foo.png"), index=1, total=1)  -> a/b/foo.png
        numbered_path(Path("a/b/foo.png"), index=1, total=4)  -> a/b/foo-1.png
        numbered_path(Path("a/b/foo.png"), index=10, total=10)-> a/b/foo-10.png

    Index is 1-based per the convention in tool docs. Padding width is
    ``len(str(total))`` so the lexicographic sort of the file system
    matches numerical order.
    """
    if total == 1:
        return base
    width = len(str(total))
    suffix = f"-{index:0{width}d}"
    return base.with_name(f"{base.stem}{suffix}{base.suffix}")


# -----------------------------------------------------------------------------
# Atomic write
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WriteResult:
    """What happened on a single output write.

    Returned to the caller (typically the tool dispatch layer) so the
    sidecar can record the bytes and the dispatch can include the path
    in the response.
    """

    path: Path
    size_bytes: int


def write_atomic(target: Path, payload: bytes, *, overwrite: bool = False) -> WriteResult:
    """Write ``payload`` to ``target`` via tmp+fsync+rename.

    If ``target`` exists and ``overwrite`` is False, raises
    :class:`OutputExists`. If overwrite is True, the rename replaces
    the existing file in one atomic operation (POSIX rename / Windows
    MoveFileEx via ``os.replace``).

    Always raises on any I/O failure; never returns partial state.
    """
    if target.exists() and not overwrite:
        raise OutputExists(f"output path already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=target.name + ".",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
    return WriteResult(path=target, size_bytes=target.stat().st_size)


# -----------------------------------------------------------------------------
# Integrity verification
# -----------------------------------------------------------------------------


_VerifyMode = Literal["png", "any"]


def verify_image(path: Path, *, mode: _VerifyMode = "png") -> None:
    """Re-decode ``path`` and assert it parses cleanly. Raises on failure.

    For PNG outputs (the default), uses Pillow's ``Image.verify()`` which
    re-parses chunks and validates CRCs without decoding pixel data —
    fast, sufficient for catching truncated or corrupted writes.

    On corruption, the file is UNLINKED (so the user never picks up a
    bad output by accident) and :class:`OutputCorrupt` is raised.
    """
    try:
        from PIL import Image, UnidentifiedImageError
        with Image.open(path) as im:
            im.verify()
            if mode == "png" and (im.format or "").upper() != "PNG":
                raise OutputCorrupt(
                    f"expected PNG output at {path} but Pillow reports "
                    f"format={im.format!r}"
                )
    except (UnidentifiedImageError, OSError, OutputCorrupt) as e:
        # Unlink the bad file before raising — the user must not pick up
        # a partial / corrupt output by mistake.
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise OutputCorrupt(
            f"output at {path} did not pass integrity verification: {e}"
        ) from e


def write_and_verify(
    target: Path,
    payload: bytes,
    *,
    overwrite: bool = False,
    verify_mode: _VerifyMode = "png",
) -> WriteResult:
    """Combined helper: atomic write + post-write integrity check.

    On verification failure the unlink is already done by
    :func:`verify_image`, so the caller only needs to surface the
    raised exception.
    """
    result = write_atomic(target, payload, overwrite=overwrite)
    verify_image(target, mode=verify_mode)
    return result


__all__ = [
    "OutputCorrupt",
    "OutputError",
    "OutputExists",
    "WriteResult",
    "numbered_path",
    "verify_image",
    "write_and_verify",
    "write_atomic",
]
