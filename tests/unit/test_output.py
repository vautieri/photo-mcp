"""Atomic output write + integrity verification tests.

FR-5.2..5.4, FR-6.7, IR-3.2, QR-7.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

from photo_mcp import output


# -----------------------------------------------------------------------------
# numbered_path
# -----------------------------------------------------------------------------


def test_numbered_path_n1_returns_base_unchanged() -> None:
    base = Path("a/b/foo.png")
    assert output.numbered_path(base, index=1, total=1) == base


def test_numbered_path_pads_to_width_of_total() -> None:
    base = Path("foo.png")
    assert output.numbered_path(base, index=1,  total=4)  == Path("foo-1.png")
    assert output.numbered_path(base, index=4,  total=4)  == Path("foo-4.png")
    assert output.numbered_path(base, index=1,  total=10) == Path("foo-01.png")
    assert output.numbered_path(base, index=10, total=10) == Path("foo-10.png")
    assert output.numbered_path(base, index=1,  total=100) == Path("foo-001.png")


def test_numbered_path_keeps_directory() -> None:
    base = Path("/tmp/dir/foo.png")
    p = output.numbered_path(base, index=2, total=3)
    assert p.parent == Path("/tmp/dir")
    assert p.name == "foo-2.png"


def test_numbered_path_handles_no_extension() -> None:
    base = Path("foo")
    p = output.numbered_path(base, index=1, total=2)
    assert p.name == "foo-1"


# -----------------------------------------------------------------------------
# write_atomic
# -----------------------------------------------------------------------------


def test_write_atomic_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "out.png"
    payload = b"\x89PNG\r\n\x1a\nbody"
    result = output.write_atomic(target, payload)
    assert result.path == target
    assert result.size_bytes == len(payload)
    assert target.read_bytes() == payload


def test_write_atomic_creates_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "out.png"
    output.write_atomic(target, b"data")
    assert target.exists()


def test_write_atomic_refuses_existing_without_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "out.png"
    target.write_bytes(b"existing")
    with pytest.raises(output.OutputExists):
        output.write_atomic(target, b"new")
    # Existing content untouched.
    assert target.read_bytes() == b"existing"


def test_write_atomic_overwrites_when_allowed(tmp_path: Path) -> None:
    target = tmp_path / "out.png"
    target.write_bytes(b"existing")
    output.write_atomic(target, b"new", overwrite=True)
    assert target.read_bytes() == b"new"


def test_write_atomic_leaves_no_tmp_files_on_success(tmp_path: Path) -> None:
    target = tmp_path / "out.png"
    output.write_atomic(target, b"payload")
    leftovers = list(target.parent.glob(f"{target.name}.*.tmp"))
    assert leftovers == []


# -----------------------------------------------------------------------------
# verify_image
# -----------------------------------------------------------------------------


def _png_bytes_solid_color(width: int, height: int) -> bytes:
    """Synthesize a small valid PNG for tests (no external assets)."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(120, 80, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def test_verify_image_passes_on_valid_png(tmp_path: Path) -> None:
    target = tmp_path / "ok.png"
    target.write_bytes(_png_bytes_solid_color(8, 8))
    output.verify_image(target)  # must not raise


def test_verify_image_unlinks_corrupt_file(tmp_path: Path) -> None:
    target = tmp_path / "bad.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\nclearly-not-a-real-png")
    with pytest.raises(output.OutputCorrupt):
        output.verify_image(target)
    # File must be unlinked so the user can't pick up the corrupt output.
    assert not target.exists()


def test_verify_image_rejects_wrong_format_when_mode_png(tmp_path: Path) -> None:
    """If we ask for PNG verification but the file is JPEG, that's a corruption.

    The atomic-writer writes whatever the API returned; if the API said
    PNG but actually returned JPEG, we want to catch it before the
    sidecar gets written.
    """
    from PIL import Image
    target = tmp_path / "actually.jpg"
    img = Image.new("RGB", (8, 8), color=(200, 100, 50))
    img.save(target, format="JPEG")
    # Renaming to .png suffix doesn't change what Pillow sees inside.
    misnamed = tmp_path / "actually.png"
    target.replace(misnamed)
    with pytest.raises(output.OutputCorrupt):
        output.verify_image(misnamed, mode="png")
    # Corrupt-on-purpose unlinks the file.
    assert not misnamed.exists()


def test_verify_image_any_mode_accepts_jpeg(tmp_path: Path) -> None:
    """``mode='any'`` skips the format check; the JPEG is structurally valid."""
    from PIL import Image
    target = tmp_path / "ok.jpg"
    Image.new("RGB", (8, 8), color=(0, 0, 0)).save(target, format="JPEG")
    output.verify_image(target, mode="any")  # must not raise


# -----------------------------------------------------------------------------
# write_and_verify
# -----------------------------------------------------------------------------


def test_write_and_verify_happy_path(tmp_path: Path) -> None:
    target = tmp_path / "ok.png"
    output.write_and_verify(target, _png_bytes_solid_color(4, 4))
    assert target.exists()


def test_write_and_verify_unlinks_on_corruption(tmp_path: Path) -> None:
    target = tmp_path / "bad.png"
    with pytest.raises(output.OutputCorrupt):
        output.write_and_verify(target, b"\x89PNG\r\n\x1a\nnot-real-data")
    assert not target.exists()
