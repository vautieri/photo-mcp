"""EXIF / IPTC / XMP capture and re-attachment.

QR-2..4 + FR-6.1..6.2: every edit/composite operation captures the
photographer's metadata BEFORE upload and re-attaches it to the output
AFTER download. The OpenAI API strips all metadata; this module is what
puts it back.

Design choices:

- **EXIF** via piexif (cross-platform, pure-Python, no external bins).
  Supports JPEG and PNG (PNG via tEXt/iTXt round-trip).
- **IPTC** via iptcinfo3 — supports JPEG only on the read side; for PNG
  outputs, IPTC is not stored (the format doesn't have a native IPTC box).
- **XMP** is optional; we degrade gracefully if `python-xmp-toolkit` is
  not installed (logged as a startup warning).

Critical fields the photographer cares about (per requirements QR-2..4):

    DateTime, Make, Model, LensModel, FocalLength, FNumber, ExposureTime,
    ISO, GPSLatitude, GPSLongitude, Copyright, Artist, dc:rights,
    dc:creator, dc:title, dc:description, IPTC By-line, Caption-Abstract.

We round-trip these explicitly. Other tags are also preserved when the
container format permits, but we only assert the critical set in tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import piexif  # type: ignore[import-untyped]
    _PIEXIF_AVAILABLE = True
except ImportError:  # pragma: no cover
    piexif = None  # type: ignore[assignment]
    _PIEXIF_AVAILABLE = False

try:
    from iptcinfo3 import IPTCInfo  # type: ignore[import-untyped]
    _IPTC_AVAILABLE = True
except ImportError:  # pragma: no cover
    IPTCInfo = None  # type: ignore[assignment]
    _IPTC_AVAILABLE = False

try:
    from libxmp import XMPFiles  # type: ignore[import-untyped]
    _XMP_AVAILABLE = True
except ImportError:  # python-xmp-toolkit is optional per pyproject extras
    XMPFiles = None  # type: ignore[assignment]
    _XMP_AVAILABLE = False


# -----------------------------------------------------------------------------
# Captured metadata snapshot
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class MetadataSnapshot:
    """In-memory metadata captured from a source file.

    Stored opaquely (raw bytes / dicts as the underlying library returned
    them) so the re-attach step can pass them back without lossy
    intermediate transformations.
    """

    source_path: Path
    source_format: str   # "jpeg" | "png" | "tiff" | "webp" | other
    exif_bytes: bytes | None = None
    iptc_data: dict[str, Any] | None = None
    xmp_packet: str | None = None
    has_exif: bool = False
    has_iptc: bool = False
    has_xmp: bool = False
    warnings: list[str] = field(default_factory=list)


# -----------------------------------------------------------------------------
# Capture
# -----------------------------------------------------------------------------


def capture(source: Path) -> MetadataSnapshot:
    """Read all available metadata from ``source`` into a snapshot.

    Never raises on missing tags or libraries — degraded captures are
    represented in the returned snapshot's ``warnings`` and ``has_*``
    flags. The caller decides how to surface them.
    """
    fmt = _detect_format(source)
    snap = MetadataSnapshot(source_path=source, source_format=fmt)

    if _PIEXIF_AVAILABLE and fmt in {"jpeg", "tiff"}:
        try:
            exif_dict = piexif.load(str(source))
            snap.exif_bytes = piexif.dump(exif_dict)
            snap.has_exif = True
        except Exception as e:  # noqa: BLE001
            snap.warnings.append(f"EXIF capture failed: {e}")
    elif fmt == "png":
        # PNG EXIF lives in an eXIf chunk in newer tools or in tEXt fields.
        # Pillow can read it but piexif on PNG requires Pillow integration.
        try:
            from PIL import Image
            with Image.open(source) as im:
                # Pillow exposes EXIF as a dict-like; we serialize via piexif.
                exif = im.getexif()
                if exif and _PIEXIF_AVAILABLE:
                    snap.exif_bytes = piexif.dump(_pillow_exif_to_piexif_dict(exif))
                    snap.has_exif = True
        except Exception as e:  # noqa: BLE001
            snap.warnings.append(f"PNG EXIF capture failed: {e}")

    if _IPTC_AVAILABLE and fmt == "jpeg":
        try:
            info = IPTCInfo(str(source), force=True, inp_charset="utf-8")
            iptc: dict[str, Any] = {}
            # Critical fields the photographer cares about.
            for tag in (
                "by-line",
                "by-line title",
                "caption/abstract",
                "copyright notice",
                "credit",
                "object name",
                "headline",
            ):
                val = info[tag]
                if val:
                    iptc[tag] = val
            if iptc:
                snap.iptc_data = iptc
                snap.has_iptc = True
        except Exception as e:  # noqa: BLE001
            snap.warnings.append(f"IPTC capture failed: {e}")

    if _XMP_AVAILABLE and fmt in {"jpeg", "tiff", "png"}:
        try:
            xmpf = XMPFiles(file_path=str(source), open_forupdate=False)
            xmp = xmpf.get_xmp()
            if xmp is not None:
                snap.xmp_packet = xmp.serialize_to_str()
                snap.has_xmp = True
            xmpf.close_file()
        except Exception as e:  # noqa: BLE001
            snap.warnings.append(f"XMP capture failed: {e}")

    return snap


# -----------------------------------------------------------------------------
# Re-attach
# -----------------------------------------------------------------------------


def reattach(snapshot: MetadataSnapshot, target: Path) -> list[str]:
    """Apply ``snapshot`` to ``target``. Returns a list of warnings.

    Critical fields are written when the target format supports them.
    The function does NOT modify the file's pixel content — only its
    metadata containers — so this is safe to run after the output is
    fully written and verified.
    """
    warnings: list[str] = []
    target_fmt = _detect_format(target)

    if snapshot.has_exif and snapshot.exif_bytes and _PIEXIF_AVAILABLE:
        try:
            piexif.insert(snapshot.exif_bytes, str(target))
        except Exception as e:  # noqa: BLE001
            warnings.append(f"EXIF re-attach to {target.name} failed: {e}")

    if snapshot.has_iptc and snapshot.iptc_data and target_fmt == "jpeg" and _IPTC_AVAILABLE:
        try:
            info = IPTCInfo(str(target), force=True, inp_charset="utf-8")
            for tag, val in snapshot.iptc_data.items():
                info[tag] = val
            info.save_as(str(target))
        except Exception as e:  # noqa: BLE001
            warnings.append(f"IPTC re-attach to {target.name} failed: {e}")

    if snapshot.has_xmp and snapshot.xmp_packet and _XMP_AVAILABLE and target_fmt in {"jpeg", "tiff", "png"}:
        try:
            xmpf = XMPFiles(file_path=str(target), open_forupdate=True)
            from libxmp import XMPMeta  # type: ignore[import-untyped]
            xmp = XMPMeta()
            xmp.parse_from_str(snapshot.xmp_packet)
            if xmpf.can_put_xmp(xmp):
                xmpf.put_xmp(xmp)
            xmpf.close_file()
        except Exception as e:  # noqa: BLE001
            warnings.append(f"XMP re-attach to {target.name} failed: {e}")

    return warnings


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


_FORMAT_BY_SUFFIX: dict[str, str] = {
    ".jpg":  "jpeg",
    ".jpeg": "jpeg",
    ".jpe":  "jpeg",
    ".png":  "png",
    ".tif":  "tiff",
    ".tiff": "tiff",
    ".webp": "webp",
}


def _detect_format(path: Path) -> str:
    return _FORMAT_BY_SUFFIX.get(path.suffix.lower(), "unknown")


def _pillow_exif_to_piexif_dict(pillow_exif: Any) -> dict[str, dict[int, Any]]:
    """Convert Pillow's flat EXIF dict to piexif's IFD-structured dict.

    Pillow returns ``{tag_id: value}``; piexif expects nested IFDs
    (``{"0th": {...}, "Exif": {...}, ...}``). This helper does a
    minimal conversion sufficient for round-trip preservation. Tags
    Pillow doesn't decode are dropped silently (we'd rather lose
    obscure tags than fail the whole reattach).
    """
    if not _PIEXIF_AVAILABLE:
        return {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "Interop": {}, "thumbnail": None}
    result: dict[str, dict[int, Any]] = {
        "0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "Interop": {}, "thumbnail": None,
    }
    for tag, value in pillow_exif.items():
        # Most photographer-critical tags live in the 0th or Exif IFD.
        if tag in piexif.TAGS["0th"]:
            result["0th"][tag] = value
        elif tag in piexif.TAGS["Exif"]:
            result["Exif"][tag] = value
        elif tag in piexif.TAGS["GPS"]:
            result["GPS"][tag] = value
        # Tags not in the standard table are dropped — explicit decision.
    return result


__all__ = [
    "MetadataSnapshot",
    "capture",
    "reattach",
]
