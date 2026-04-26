"""Path-policy tests.

NFR-3.3..3.7: input and output paths are canonicalized, allow-listed,
device paths and symlinks are rejected unless explicitly enabled. These
tests cover the policy class directly; integration with tool dispatch
is tested separately.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from photo_mcp import paths as p


# -----------------------------------------------------------------------------
# Input path canonicalization
# -----------------------------------------------------------------------------


def test_input_under_root_accepted(tmp_path: Path) -> None:
    src = tmp_path / "photo.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n")
    pol = p.PathPolicy(allowed_input_roots=(tmp_path,))
    resolved = pol.canonicalize_input(src)
    assert resolved == src.resolve()


def test_input_outside_roots_rejected(tmp_path: Path) -> None:
    inside = tmp_path / "ok"
    inside.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    src = other / "photo.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n")
    pol = p.PathPolicy(allowed_input_roots=(inside,))
    with pytest.raises(p.PathOutsideRoots):
        pol.canonicalize_input(src)


def test_input_does_not_exist_rejected(tmp_path: Path) -> None:
    pol = p.PathPolicy(allowed_input_roots=(tmp_path,))
    with pytest.raises(p.PathDoesNotExist):
        pol.canonicalize_input(tmp_path / "nope.png")


def test_input_empty_path_rejected(tmp_path: Path) -> None:
    pol = p.PathPolicy(allowed_input_roots=(tmp_path,))
    with pytest.raises(p.PathDoesNotExist):
        pol.canonicalize_input("")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX device-path block list")
def test_input_dev_path_rejected(tmp_path: Path) -> None:
    pol = p.PathPolicy(allowed_input_roots=(Path("/"),))
    with pytest.raises(p.PathBlockedDevice):
        pol.canonicalize_input("/dev/null")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink semantics")
def test_input_symlink_rejected_by_default(tmp_path: Path) -> None:
    target = tmp_path / "real.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\n")
    link = tmp_path / "link.png"
    os.symlink(target, link)
    pol = p.PathPolicy(allowed_input_roots=(tmp_path,))
    with pytest.raises(p.PathIsSymlink):
        pol.canonicalize_input(link)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink semantics")
def test_input_symlink_accepted_when_enabled(tmp_path: Path) -> None:
    target = tmp_path / "real.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\n")
    link = tmp_path / "link.png"
    os.symlink(target, link)
    pol = p.PathPolicy(allowed_input_roots=(tmp_path,), follow_symlinks=True)
    resolved = pol.canonicalize_input(link)
    assert resolved == target.resolve()


def test_input_default_roots_uses_home() -> None:
    pol = p.PathPolicy()  # empty roots → falls back to home
    # File in home dir would be accepted (we don't actually create one);
    # a file in a sibling root must be rejected. Just check that the
    # fallback behavior triggers — no exception on a known-good input
    # file under home is the test, but writing into ~/ is rude in tests.
    # Instead, verify the policy reports the expected fallback root.
    assert pol._input_roots() == (Path.home().resolve(),)


# -----------------------------------------------------------------------------
# Output path canonicalization
# -----------------------------------------------------------------------------


def test_output_under_root_accepted(tmp_path: Path) -> None:
    pol = p.PathPolicy(allowed_output_roots=(tmp_path,))
    resolved = pol.canonicalize_output(tmp_path / "out.png")
    assert resolved == (tmp_path.resolve() / "out.png")


def test_output_outside_roots_rejected(tmp_path: Path) -> None:
    inside = tmp_path / "ok"
    inside.mkdir()
    pol = p.PathPolicy(allowed_output_roots=(inside,))
    with pytest.raises(p.PathOutsideRoots):
        pol.canonicalize_output(tmp_path / "elsewhere.png")


def test_output_parent_must_exist(tmp_path: Path) -> None:
    pol = p.PathPolicy(allowed_output_roots=(tmp_path,))
    with pytest.raises(p.PathDoesNotExist):
        pol.canonicalize_output(tmp_path / "missing-dir" / "out.png")


def test_output_can_target_nonexistent_file(tmp_path: Path) -> None:
    pol = p.PathPolicy(allowed_output_roots=(tmp_path,))
    target = tmp_path / "not-yet.png"
    assert not target.exists()
    resolved = pol.canonicalize_output(target)
    assert resolved == target.resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX device-path block list")
def test_output_dev_path_rejected() -> None:
    pol = p.PathPolicy(allowed_output_roots=(Path("/"),))
    with pytest.raises(p.PathBlockedDevice):
        pol.canonicalize_output("/dev/null")


# -----------------------------------------------------------------------------
# Multiple roots
# -----------------------------------------------------------------------------


def test_multiple_roots_first_match_wins(tmp_path: Path) -> None:
    a = tmp_path / "a"
    a.mkdir()
    b = tmp_path / "b"
    b.mkdir()
    pol = p.PathPolicy(allowed_input_roots=(a, b))
    src = b / "photo.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n")
    # Should be accepted because it's under root b.
    resolved = pol.canonicalize_input(src)
    assert resolved == src.resolve()


# -----------------------------------------------------------------------------
# PathError.to_dict
# -----------------------------------------------------------------------------


def test_path_error_to_dict_carries_type() -> None:
    err = p.PathOutsideRoots("hello")
    d = err.to_dict()
    assert d["type"] == "path_outside_roots"
    assert d["message"] == "hello"


def test_each_subclass_has_unique_error_type() -> None:
    types = {
        cls.error_type
        for cls in (
            p.PathError,
            p.PathOutsideRoots,
            p.PathIsSymlink,
            p.PathBlockedDevice,
            p.PathDoesNotExist,
        )
    }
    # All subclasses must override; PathError itself shares with no one.
    assert len(types) == 5
