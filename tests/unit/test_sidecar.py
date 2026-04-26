"""Provenance sidecar tests.

QR-10..12: every output writes a sibling JSON sidecar with SHA-256 of
every source, the prompt, model, parameters, SSIM, and cost. Atomic
write so a crash mid-write never leaves a half-sidecar.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from photo_mcp import sidecar


# -----------------------------------------------------------------------------
# SourceRef.from_file
# -----------------------------------------------------------------------------


def test_source_ref_captures_size_and_hash(tmp_path: Path) -> None:
    src = tmp_path / "x.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\nhelloworld")
    ref = sidecar.SourceRef.from_file(src)
    assert ref.path == src
    assert ref.size_bytes == len(b"\x89PNG\r\n\x1a\nhelloworld")
    assert ref.sha256 == sidecar.hash_bytes(b"\x89PNG\r\n\x1a\nhelloworld")
    assert ref.mime == "image/png"


def test_source_ref_to_dict_round_trips(tmp_path: Path) -> None:
    src = tmp_path / "x.jpg"
    src.write_bytes(b"\xff\xd8\xff\xe0\x00data")
    ref = sidecar.SourceRef.from_file(src)
    d = ref.to_dict()
    assert d["path"] == str(src)
    assert d["sha256"] == ref.sha256
    assert d["size_bytes"] == ref.size_bytes
    assert d["mime"] == "image/jpeg"


def test_hash_file_matches_hash_bytes(tmp_path: Path) -> None:
    """Streamed file hash and direct bytes hash must be identical."""
    payload = b"the quick brown fox" * 1000
    src = tmp_path / "data.bin"
    src.write_bytes(payload)
    assert sidecar.hash_file(src) == sidecar.hash_bytes(payload)


# -----------------------------------------------------------------------------
# Sidecar.to_dict + write_sidecar
# -----------------------------------------------------------------------------


def _make_sidecar(tmp_path: Path) -> tuple[sidecar.Sidecar, Path]:
    src = tmp_path / "src.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\nsource")
    out_path = tmp_path / "out.png"
    out_path.write_bytes(b"\x89PNG\r\n\x1a\noutput")
    return (
        sidecar.Sidecar(
            tool="edit",
            model="gpt-image-2",
            endpoint="edits",
            prompt="replace the sky",
            parameters={"quality": "high", "n": 1},
            sources=[sidecar.SourceRef.from_file(src)],
            output_path=out_path,
            output_sha256=sidecar.hash_file(out_path),
            output_size_bytes=out_path.stat().st_size,
            cost_usd_estimate=0.165,
            request_ms=4127,
            ssim_to_image_0=0.97,
            metadata_preserved_from=src,
            color_profile_preserved_from=src,
            color_profile_name="sRGB",
        ),
        out_path,
    )


def test_to_dict_contains_all_critical_fields(tmp_path: Path) -> None:
    s, _ = _make_sidecar(tmp_path)
    d = s.to_dict()
    # Mandatory top-level keys per the schema docs (system design §5.3).
    for key in (
        "$schema", "version", "photo_mcp_version", "created_at", "tool",
        "model", "endpoint", "prompt", "parameters", "sources", "output",
        "ssim_to_image_0", "metadata_preserved_from",
        "color_profile_preserved_from", "color_profile_name",
        "warnings", "cost_usd_estimate", "request_ms",
    ):
        assert key in d, f"missing key: {key}"
    # Output sub-record
    for key in ("path", "sha256", "size_bytes"):
        assert key in d["output"]
    # Source sub-record
    assert isinstance(d["sources"], list)
    assert d["sources"][0]["sha256"]
    assert d["sources"][0]["size_bytes"] > 0


def test_to_dict_path_objects_become_strings(tmp_path: Path) -> None:
    s, _ = _make_sidecar(tmp_path)
    d = s.to_dict()
    assert isinstance(d["sources"][0]["path"], str)
    assert isinstance(d["output"]["path"], str)
    assert isinstance(d["metadata_preserved_from"], str)


def test_to_dict_created_at_iso_utc(tmp_path: Path) -> None:
    s, _ = _make_sidecar(tmp_path)
    d = s.to_dict()
    ts = d["created_at"]
    assert ts.endswith("Z") or ts.endswith("+00:00") or "Z" in ts


def test_to_dict_with_no_mask_emits_null(tmp_path: Path) -> None:
    s, _ = _make_sidecar(tmp_path)
    d = s.to_dict()
    assert d["mask"] is None


# -----------------------------------------------------------------------------
# write_sidecar
# -----------------------------------------------------------------------------


def test_sidecar_path_for() -> None:
    p = Path("/some/dir/photo.png")
    assert sidecar.sidecar_path_for(p).name == "photo.png.photo-mcp.json"
    assert sidecar.sidecar_path_for(p).parent == p.parent


def test_write_sidecar_atomic_creates_file(tmp_path: Path) -> None:
    s, out_path = _make_sidecar(tmp_path)
    target = sidecar.write_sidecar(s)
    assert target.exists()
    assert target.name == out_path.name + ".photo-mcp.json"


def test_write_sidecar_payload_is_parseable_json(tmp_path: Path) -> None:
    s, _ = _make_sidecar(tmp_path)
    target = sidecar.write_sidecar(s)
    parsed = json.loads(target.read_text(encoding="utf-8"))
    assert parsed["model"] == "gpt-image-2"
    assert parsed["prompt"] == "replace the sky"


def test_write_sidecar_does_not_leave_tmp_files_on_success(tmp_path: Path) -> None:
    s, out_path = _make_sidecar(tmp_path)
    sidecar.write_sidecar(s)
    # No leftover .tmp files in the parent dir.
    leftovers = list(out_path.parent.glob(f"{out_path.name}.*.tmp"))
    assert leftovers == [], f"unexpected tmp files: {leftovers}"


def test_write_sidecar_overwrites_existing_atomically(tmp_path: Path) -> None:
    s, out_path = _make_sidecar(tmp_path)
    sidecar.write_sidecar(s)
    # Mutate the parameters and write again — sidecar must reflect the new state.
    s.prompt = "different prompt"
    target = sidecar.write_sidecar(s)
    parsed = json.loads(target.read_text(encoding="utf-8"))
    assert parsed["prompt"] == "different prompt"


def test_write_sidecar_records_each_source_sha(tmp_path: Path) -> None:
    """The whole point of QR-10: each source's SHA-256 must be in the sidecar."""
    src1 = tmp_path / "a.png"
    src1.write_bytes(b"alpha")
    src2 = tmp_path / "b.png"
    src2.write_bytes(b"beta")
    out = tmp_path / "merged.png"
    out.write_bytes(b"merged")
    s = sidecar.Sidecar(
        tool="edit",
        model="gpt-image-2",
        endpoint="edits",
        prompt="merge",
        parameters={},
        sources=[sidecar.SourceRef.from_file(src1), sidecar.SourceRef.from_file(src2)],
        output_path=out,
        output_sha256=sidecar.hash_file(out),
        output_size_bytes=out.stat().st_size,
        cost_usd_estimate=0.05,
        request_ms=2000,
    )
    target = sidecar.write_sidecar(s)
    parsed = json.loads(target.read_text(encoding="utf-8"))
    assert len(parsed["sources"]) == 2
    assert parsed["sources"][0]["sha256"] == sidecar.hash_bytes(b"alpha")
    assert parsed["sources"][1]["sha256"] == sidecar.hash_bytes(b"beta")


def test_audit_round_trip_recoverable_via_sha(tmp_path: Path) -> None:
    """WS-7 acceptance: the sidecar lets a future reader prove source identity.

    Steps:
      1. write the sidecar
      2. months later the photographer wants to verify
      3. hash each source path the sidecar recorded; compare to the SHA in the
         sidecar
      4. equality => the same file IS the original; mismatch => has been
         altered (or someone replaced it)
    """
    s, _ = _make_sidecar(tmp_path)
    target = sidecar.write_sidecar(s)
    parsed = json.loads(target.read_text(encoding="utf-8"))

    for entry in parsed["sources"]:
        on_disk_now = sidecar.hash_file(Path(entry["path"]))
        assert on_disk_now == entry["sha256"], (
            f"audit failed for {entry['path']!r}: expected {entry['sha256']}, "
            f"got {on_disk_now}"
        )
