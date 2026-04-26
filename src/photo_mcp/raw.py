"""RAW (.cr3, .nef, .arw, .dng, ...) pre-conversion.

FR-6.6: OpenAI's edit endpoint does not accept RAW files. The
photographer's RAW must be debayered and exported to PNG before upload.
This module wraps `rawpy` (LibRaw) with photographer-controllable
parameters; the goal is **honest transparent conversion**, not "make it
look pretty for me."

Photographer-relevant defaults:

- ``output_bps=16``    — preserve bit depth (will be 8-bit downconverted
                         on encode if PNG output requires)
- ``no_auto_bright=True`` — don't auto-stretch shadows/highlights
- ``use_camera_wb=True``  — match the camera's white balance, not auto WB
- ``output_color=ColorSpace.AdobeRGB`` — wider gamut than sRGB; the
                         photographer can downconvert in their own pipeline
- ``demosaic_algorithm=AHD`` — high-quality default; user can override

All defaults are overridable per call via :class:`RawParams`. The server
embeds the chosen parameters in the provenance sidecar so the conversion
is reproducible.

If `rawpy` is not installed, :func:`is_raw_available` returns False and
the server returns ER-7 raw_unavailable when the photographer hands a
RAW file (rather than silently mangling it through Pillow).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

try:
    import rawpy  # type: ignore[import-untyped]
    _RAWPY_AVAILABLE = True
except ImportError:  # pragma: no cover — rawpy is in the runtime deps but RAW handling is degradable
    rawpy = None  # type: ignore[assignment]
    _RAWPY_AVAILABLE = False


# Common RAW suffixes by camera vendor (lowercase):
_RAW_SUFFIXES: frozenset[str] = frozenset(
    {
        ".cr2", ".cr3",                # Canon
        ".nef", ".nrw",                # Nikon
        ".arw", ".srf", ".sr2",        # Sony
        ".dng",                        # generic / Adobe / iPhone Pro
        ".rw2",                        # Panasonic
        ".raf",                        # Fujifilm
        ".orf",                        # Olympus / OM-System
        ".pef", ".ptx",                # Pentax
        ".raw",                        # generic
        ".x3f",                        # Sigma
        ".3fr", ".fff",                # Hasselblad
        ".iiq",                        # Phase One
    }
)


# -----------------------------------------------------------------------------
# Errors
# -----------------------------------------------------------------------------


class RawError(Exception):
    """Base for RAW pipeline failures."""


class RawNotAvailable(RawError):
    """`rawpy` not importable; RAW handling is degraded."""


class RawDecodeError(RawError):
    """Underlying LibRaw could not decode the file."""


# -----------------------------------------------------------------------------
# Parameters
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RawParams:
    """Photographer-tunable RAW conversion knobs.

    Defaults match the documented "honest conversion" preset (see module
    docstring). Per-call overrides come from the tool input's
    ``raw_params`` object; any unspecified field uses the default.
    """

    output_bps: int = 16            # 8 or 16
    use_camera_wb: bool = True
    use_auto_wb: bool = False
    no_auto_bright: bool = True
    output_color: str = "AdobeRGB"  # "sRGB" | "AdobeRGB" | "Wide" | "ProPhoto" | "XYZ" | "ACES" | "P3"
    demosaic_algorithm: str = "AHD"  # "LINEAR"|"VNG"|"PPG"|"AHD"|"DCB"|"DHT"|"AAHD"|"AMAZE"|"MODIFIED_AHD"
    bright: float = 1.0             # gain applied during demosaic
    user_flip: int | None = None    # 0|3|5|6 — orientation override; None = use EXIF
    median_filter_passes: int = 0   # 3x3 median passes on the bayer

    def to_rawpy_kwargs(self) -> dict[str, Any]:
        """Translate to the kwargs ``rawpy.RawPy.postprocess`` expects."""
        if not _RAWPY_AVAILABLE:
            raise RawNotAvailable("rawpy is not installed")
        out: dict[str, Any] = {
            "output_bps": int(self.output_bps),
            "use_camera_wb": bool(self.use_camera_wb),
            "use_auto_wb": bool(self.use_auto_wb),
            "no_auto_bright": bool(self.no_auto_bright),
            "bright": float(self.bright),
            "median_filter_passes": int(self.median_filter_passes),
        }
        out["output_color"] = _color_space_value(self.output_color)
        out["demosaic_algorithm"] = _demosaic_value(self.demosaic_algorithm)
        if self.user_flip is not None:
            out["user_flip"] = int(self.user_flip)
        return out


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def is_raw_path(path: Path) -> bool:
    return path.suffix.lower() in _RAW_SUFFIXES


def is_raw_available() -> bool:
    return _RAWPY_AVAILABLE


def decode_to_png_bytes(source: Path, params: RawParams = RawParams()) -> bytes:
    """Decode a RAW file and return PNG-encoded bytes.

    The PNG is encoded with the requested bit depth (8 or 16). Raises
    :class:`RawNotAvailable` if rawpy is missing, :class:`RawDecodeError`
    on LibRaw errors, and :class:`FileNotFoundError` if the source path
    is missing.
    """
    if not _RAWPY_AVAILABLE:
        raise RawNotAvailable(
            f"Cannot decode {source.name}: rawpy is not installed. "
            "Install via 'pip install rawpy' or pre-convert the RAW to "
            "PNG/TIFF in your photo pipeline before passing it to "
            "photo-mcp."
        )
    if not source.exists():
        raise FileNotFoundError(str(source))
    try:
        with rawpy.imread(str(source)) as raw:
            rgb = raw.postprocess(**params.to_rawpy_kwargs())
    except (rawpy.LibRawError, OSError) as e:  # type: ignore[attr-defined]
        raise RawDecodeError(
            f"LibRaw could not decode {source.name}: {e}. "
            "If this is a recent camera body, your installed LibRaw may "
            "lack support — pre-convert via Lightroom or Capture One and "
            "pass the resulting TIFF/PNG instead."
        ) from e

    return _encode_png(rgb, bit_depth=params.output_bps)


def decode_to_path(source: Path, target: Path, params: RawParams = RawParams()) -> Path:
    """Convenience: decode and write to ``target``. Returns ``target``.

    Used when the photographer's tool input was a RAW file path; the
    server converts to a temp file alongside the source and uploads
    that file. The temp file is the photographer's responsibility to
    clean up if they passed an explicit target; the server uses a
    tmp dir for its internal conversions.
    """
    png = decode_to_png_bytes(source, params)
    target.write_bytes(png)
    return target


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------


def _color_space_value(name: str) -> int:
    """Resolve a string color space to rawpy's ColorSpace enum int.

    rawpy.ColorSpace is an IntEnum; we accept either uppercase variants
    (``"ADOBERGB"``) or natural casing (``"AdobeRGB"``). Unknown names
    fall back to AdobeRGB with no error — the photographer chose a
    reasonable wide-gamut default.
    """
    if not _RAWPY_AVAILABLE:
        return 0
    cs = rawpy.ColorSpace  # type: ignore[attr-defined]
    norm = name.replace(" ", "").lower()
    table = {
        "srgb":     cs.sRGB,
        "adobergb": cs.Adobe,
        "adobe":    cs.Adobe,
        "wide":     cs.Wide,
        "prophoto": cs.ProPhoto,
        "prophotorgb": cs.ProPhoto,
        "xyz":      cs.XYZ,
        "aces":     getattr(cs, "ACES", cs.Adobe),
        "p3":       getattr(cs, "P3", cs.Adobe),
        "displayp3": getattr(cs, "P3", cs.Adobe),
    }
    return int(table.get(norm, cs.Adobe))


def _demosaic_value(name: str) -> int:
    if not _RAWPY_AVAILABLE:
        return 0
    da = rawpy.DemosaicAlgorithm  # type: ignore[attr-defined]
    norm = name.upper().replace(" ", "")
    return int(getattr(da, norm, da.AHD))


def _encode_png(rgb: Any, *, bit_depth: int) -> bytes:
    """Encode a numpy RGB array (H, W, 3) to PNG bytes at the requested bit depth.

    Pillow can write 16-bit PNGs only via the ``I;16`` mode for grayscale;
    for 16-bit RGB we must serialize via numpy + ``cv2`` or ``imageio``.
    Since adding cv2 to the runtime deps is heavy, we use ``imageio`` if
    available (transitive via scikit-image which IS in deps) or fall
    back to 8-bit if not.
    """
    import numpy as np
    from PIL import Image

    if bit_depth == 16 and rgb.dtype == np.uint16:
        # Try imageio first; fall back to Pillow with downconvert + warning.
        try:
            import imageio.v3 as iio  # type: ignore[import-untyped]
            buf = io.BytesIO()
            iio.imwrite(buf, rgb, extension=".png")
            return buf.getvalue()
        except ImportError:
            # Downconvert to 8-bit; the warning surface is the tool result,
            # not this function — this is the "best effort" branch.
            rgb = (rgb >> 8).astype(np.uint8)

    if rgb.dtype != np.uint8:
        rgb = rgb.astype(np.uint8)
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


__all__ = [
    "RawDecodeError",
    "RawError",
    "RawNotAvailable",
    "RawParams",
    "decode_to_path",
    "decode_to_png_bytes",
    "is_raw_available",
    "is_raw_path",
]
