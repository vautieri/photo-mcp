"""ICC color profile capture and embedding.

QR-5 + FR-6.3..6.4: a non-sRGB source (AdobeRGB, ProPhoto, etc.) sees its
gamut silently shrunk by OpenAI which always returns sRGB. This module
captures the source's ICC profile and embeds it back into the output so
a color-managed application sees the right space — OR warns the user
explicitly when they didn't request preservation.

The implementation deliberately favors round-trip fidelity over format
conversion. We do NOT auto-transform colors; we just label what space
the pixels are in. If the photographer wants a color conversion they
do it in their own pipeline.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

# Common ICC profile name patterns we recognize from the embedded profile's
# "desc" tag. This is best-effort identification — Pillow exposes the raw
# bytes; we sniff the first few hundred for known signatures.
_PROFILE_SIGNATURES: tuple[tuple[str, bytes], ...] = (
    ("sRGB IEC61966-2.1",     b"sRGB IEC61966-2.1"),
    ("sRGB",                  b"sRGB"),
    ("AdobeRGB1998",          b"Adobe RGB (1998)"),
    ("AdobeRGB",              b"AdobeRGB"),
    ("ProPhotoRGB",           b"ProPhoto RGB"),
    ("ProPhotoRGB",           b"Kodak ProPhoto"),
    ("DisplayP3",             b"Display P3"),
    ("Rec2020",               b"Rec. 2020"),
    ("Rec709",                b"Rec. 709"),
)


@dataclass(frozen=True, slots=True)
class ColorProfile:
    """Captured ICC profile.

    ``raw`` is the exact bytes embedded in the source; we copy them
    verbatim so the round-trip preserves any vendor-specific extensions.
    ``identified_name`` is best-effort and may be empty for custom
    monitor profiles or generated CMYK profiles — that's fine, we still
    have the raw bytes to embed.
    """

    raw: bytes
    identified_name: str
    sha256: str
    is_srgb: bool

    @property
    def size_bytes(self) -> int:
        return len(self.raw)


# -----------------------------------------------------------------------------
# Capture
# -----------------------------------------------------------------------------


def capture(source: Path) -> ColorProfile | None:
    """Read the ICC profile bytes embedded in ``source``.

    Returns ``None`` if the file has no ICC profile (which is the
    common case for sRGB images that don't bother tagging — the
    photographer is implicitly in sRGB and no preservation is needed).

    Never raises on a missing/corrupt profile — those become None /
    fallback identification.
    """
    try:
        from PIL import Image
        with Image.open(source) as im:
            raw = im.info.get("icc_profile")
            if not raw:
                return None
            if not isinstance(raw, bytes):  # pragma: no cover — Pillow always returns bytes
                raw = bytes(raw)
            name = _identify(raw)
            return ColorProfile(
                raw=raw,
                identified_name=name,
                sha256=hashlib.sha256(raw).hexdigest(),
                is_srgb=_is_srgb(name),
            )
    except (FileNotFoundError, OSError):
        return None


# -----------------------------------------------------------------------------
# Embed
# -----------------------------------------------------------------------------


def embed(target: Path, profile: ColorProfile) -> None:
    """Embed ``profile`` into ``target``.

    Uses Pillow's ``Image.save`` round-trip with the icc_profile keyword.
    For PNG / JPEG / WebP this writes the appropriate native chunk
    (iCCP / APP2 / VP8X-bound ICCP). On other formats the call may
    silently no-op — caller should warn if QR-5 preservation was
    requested but the format doesn't support it.
    """
    from PIL import Image
    with Image.open(target) as im:
        # Re-save with the profile attached; preserve format and other
        # info that Pillow already loaded.
        save_kwargs: dict[str, object] = {"icc_profile": profile.raw}
        # Format detection from the file's actual content, not the suffix.
        fmt = im.format or _format_from_suffix(target.suffix)
        if fmt:
            save_kwargs["format"] = fmt
        # Avoid re-encoding penalties: PNG with the same compression level,
        # JPEG with quality=95 (only ever called on outputs we just wrote
        # ourselves so the source quality is already known to us).
        if fmt == "PNG":
            save_kwargs["optimize"] = False
            save_kwargs["compress_level"] = 6
        elif fmt in ("JPEG", "WEBP"):
            save_kwargs["quality"] = 95
        im.save(target, **save_kwargs)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _identify(raw: bytes) -> str:
    """Best-effort name lookup from the profile's description tag."""
    head = raw[:2048]
    for name, sig in _PROFILE_SIGNATURES:
        if sig in head:
            return name
    return ""


def _is_srgb(identified_name: str) -> bool:
    return identified_name.lower().startswith("srgb")


def _format_from_suffix(suffix: str) -> str | None:
    s = suffix.lower()
    if s in {".jpg", ".jpeg"}:
        return "JPEG"
    if s == ".png":
        return "PNG"
    if s == ".webp":
        return "WEBP"
    if s in {".tif", ".tiff"}:
        return "TIFF"
    return None


__all__ = [
    "ColorProfile",
    "capture",
    "embed",
]
