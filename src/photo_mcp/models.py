"""Capability matrix for OpenAI gpt-image models.

This module is the single source of truth for which model supports which
parameter. Tools consult :func:`capability_for` before sending a request
to the OpenAI SDK, and ``list_models`` exposes the matrix verbatim to the
LLM client so the parent agent can choose intelligently.

Spec source: ``docs/02-requirements.md`` §6 capability matrix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal, get_args

# -----------------------------------------------------------------------------
# Type aliases
# -----------------------------------------------------------------------------

ModelId = Literal[
    "gpt-image-1",
    "gpt-image-1-mini",
    "gpt-image-1.5",
    "gpt-image-2",
]

QualityLevel = Literal["low", "medium", "high", "auto"]
OutputFormat = Literal["png", "jpeg", "webp"]
BackgroundPolicy = Literal["opaque", "auto", "transparent"]
ResponseFormat = Literal["b64_json", "url"]
ModerationLevel = Literal["auto", "low"]
InputFidelity = Literal["high", "low"]

# Sizes are model-dependent; see ``Capabilities.allowed_sizes``.
SIZE_AUTO: Final = "auto"
SIZE_SQUARE_1024: Final = "1024x1024"
SIZE_LANDSCAPE_1536: Final = "1536x1024"
SIZE_PORTRAIT_1536: Final = "1024x1536"
SIZE_SQUARE_2048: Final = "2048x2048"
SIZE_LANDSCAPE_2048: Final = "2048x1152"
SIZE_LANDSCAPE_4K: Final = "3840x2160"
SIZE_PORTRAIT_4K: Final = "2160x3840"

ALL_MODELS: Final[tuple[ModelId, ...]] = get_args(ModelId)


# -----------------------------------------------------------------------------
# Capability record
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class Capabilities:
    """What a single model version supports.

    Frozen + slotted so the matrix is immutable at runtime — a tool cannot
    accidentally mutate another tool's capability view. Equality is by
    field values, useful in tests.
    """

    model: ModelId
    allowed_sizes: tuple[str, ...]
    allowed_qualities: tuple[QualityLevel, ...] = ("low", "medium", "high", "auto")
    allowed_output_formats: tuple[OutputFormat, ...] = ("png", "jpeg", "webp")
    allowed_backgrounds: tuple[BackgroundPolicy, ...] = ("opaque", "auto")
    allowed_moderations: tuple[ModerationLevel, ...] = ("auto", "low")
    # NOTE: gpt-image-* models DO NOT accept the `response_format` parameter
    # that DALL-E uses. They always return base64-encoded images. The
    # ResponseFormat alias is retained for documentation/typing only;
    # callers must NOT pass a `response_format` field to the API for these
    # models or OpenAI returns 400 unknown_parameter. See
    # https://community.openai.com/t/.../1239987 and our own incident from
    # 2026-04-25 where we passed it through and the API rejected the call.
    # The field below is kept (tuple is empty) so downstream code that
    # introspects capabilities sees a clear "no choice — always b64_json".
    allowed_response_formats: tuple[ResponseFormat, ...] = ()
    supports_input_fidelity: bool = False
    supports_streaming: bool = True
    supports_partial_images: bool = True
    supports_output_compression: bool = True
    max_input_images: int = 16  # all gpt-image models cap at 16 per /v1/images/edits
    max_input_image_bytes: int = 50 * 1024 * 1024
    max_prompt_chars: int = 32_000
    notes: tuple[str, ...] = field(default_factory=tuple)


# -----------------------------------------------------------------------------
# The matrix
# -----------------------------------------------------------------------------
#
# Every fact below is sourced from the OpenAI API docs as of 2026-04-25.
# When OpenAI revises the API the test suite ("test_models.py") will catch
# drift via cassette-replay and live-API smoke (V&V Plan §5).

_GPT_IMAGE_1: Final = Capabilities(
    model="gpt-image-1",
    allowed_sizes=(SIZE_AUTO, SIZE_SQUARE_1024, SIZE_LANDSCAPE_1536, SIZE_PORTRAIT_1536),
    allowed_backgrounds=("opaque", "auto", "transparent"),
    supports_input_fidelity=True,
    notes=(
        "First gpt-image generation; transparent background supported.",
        "input_fidelity user-selectable.",
    ),
)

_GPT_IMAGE_1_MINI: Final = Capabilities(
    model="gpt-image-1-mini",
    allowed_sizes=(SIZE_AUTO, SIZE_SQUARE_1024, SIZE_LANDSCAPE_1536, SIZE_PORTRAIT_1536),
    allowed_backgrounds=("opaque", "auto", "transparent"),
    supports_input_fidelity=True,
    notes=("Cost-optimized variant of gpt-image-1.",),
)

_GPT_IMAGE_1_5: Final = Capabilities(
    model="gpt-image-1.5",
    allowed_sizes=(SIZE_AUTO, SIZE_SQUARE_1024, SIZE_LANDSCAPE_1536, SIZE_PORTRAIT_1536),
    allowed_backgrounds=("opaque", "auto", "transparent"),
    supports_input_fidelity=True,
    notes=(
        "Quality + speed iteration over gpt-image-1.",
        "input_fidelity user-selectable; document drift caused photographer "
        "complaints — test suite asserts user value is honored.",
    ),
)

_GPT_IMAGE_2: Final = Capabilities(
    model="gpt-image-2",
    allowed_sizes=(
        SIZE_AUTO,
        SIZE_SQUARE_1024,
        SIZE_LANDSCAPE_1536,
        SIZE_PORTRAIT_1536,
        SIZE_SQUARE_2048,
        SIZE_LANDSCAPE_2048,
        SIZE_LANDSCAPE_4K,
        SIZE_PORTRAIT_4K,
    ),
    allowed_backgrounds=("opaque", "auto"),  # NO transparent on gpt-image-2
    supports_input_fidelity=False,           # always high; not user-selectable
    notes=(
        "Released 2026-04-21. Up to 4K output. Always uses high input "
        "fidelity (not configurable). Does NOT support transparent "
        "background. Strongest overall quality; most expensive.",
    ),
)

_MATRIX: Final[dict[ModelId, Capabilities]] = {
    "gpt-image-1":      _GPT_IMAGE_1,
    "gpt-image-1-mini": _GPT_IMAGE_1_MINI,
    "gpt-image-1.5":    _GPT_IMAGE_1_5,
    "gpt-image-2":      _GPT_IMAGE_2,
}


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def capability_for(model: ModelId) -> Capabilities:
    """Return the capability record for the given model identifier.

    Raises KeyError on unknown identifier (caller bug — the matrix is the
    authoritative enum). Callers should prefer the typed Literal alias to
    avoid passing arbitrary strings.
    """
    return _MATRIX[model]


def all_capabilities() -> tuple[Capabilities, ...]:
    """Return every capability record, ordered by model release lineage."""
    return (_GPT_IMAGE_1, _GPT_IMAGE_1_MINI, _GPT_IMAGE_1_5, _GPT_IMAGE_2)


def is_known_model(name: str) -> bool:
    """True iff ``name`` is in the supported model set."""
    return name in _MATRIX


# -----------------------------------------------------------------------------
# Validation helpers — used by tool input parsers (NOT a substitute for full
# input validation; these answer "is this combo allowed for this model?")
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UnsupportedParameter:
    """Structured rejection reason. Returned to the LLM as ER-3."""

    parameter: str
    value: str
    model: ModelId
    supported_models: tuple[ModelId, ...]
    hint: str = ""

    def to_message(self) -> str:
        return (
            f"Parameter {self.parameter!r}={self.value!r} is not supported by "
            f"model {self.model!r}. Supported models: "
            f"{', '.join(self.supported_models)}."
            + (f" {self.hint}" if self.hint else "")
        )


def validate_size(model: ModelId, size: str) -> UnsupportedParameter | None:
    cap = _MATRIX[model]
    if size in cap.allowed_sizes:
        return None
    return UnsupportedParameter(
        parameter="size",
        value=size,
        model=model,
        supported_models=tuple(m for m, c in _MATRIX.items() if size in c.allowed_sizes),
        hint=f"Valid sizes for {model}: {', '.join(cap.allowed_sizes)}.",
    )


def validate_background(model: ModelId, background: str) -> UnsupportedParameter | None:
    cap = _MATRIX[model]
    if background in cap.allowed_backgrounds:
        return None
    return UnsupportedParameter(
        parameter="background",
        value=background,
        model=model,
        supported_models=tuple(
            m for m, c in _MATRIX.items() if background in c.allowed_backgrounds
        ),
        hint=(
            "gpt-image-2 does not support transparent backgrounds; use "
            "gpt-image-1, gpt-image-1-mini, or gpt-image-1.5 for transparency."
            if background == "transparent" and model == "gpt-image-2"
            else ""
        ),
    )


def validate_input_fidelity(
    model: ModelId, fidelity: InputFidelity
) -> UnsupportedParameter | None:
    cap = _MATRIX[model]
    if cap.supports_input_fidelity:
        return None
    if fidelity == "high":
        # gpt-image-2 always uses high; passing high is harmless and we
        # silently accept it for ergonomic reasons (no caller wants to
        # special-case the model just to drop a parameter that already
        # matches the implicit value).
        return None
    return UnsupportedParameter(
        parameter="input_fidelity",
        value=fidelity,
        model=model,
        supported_models=tuple(m for m, c in _MATRIX.items() if c.supports_input_fidelity),
        hint=(
            "gpt-image-2 always uses high input fidelity and does not allow "
            "user override. To request lower-fidelity reinterpretation, use "
            "gpt-image-1.5 (or gpt-image-1)."
        ),
    )


__all__ = [
    "ALL_MODELS",
    "BackgroundPolicy",
    "Capabilities",
    "InputFidelity",
    "ModelId",
    "ModerationLevel",
    "OutputFormat",
    "QualityLevel",
    "ResponseFormat",
    "UnsupportedParameter",
    "all_capabilities",
    "capability_for",
    "is_known_model",
    "validate_background",
    "validate_input_fidelity",
    "validate_size",
]
