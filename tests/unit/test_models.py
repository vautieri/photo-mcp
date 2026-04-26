"""Capability matrix tests.

Verifies the matrix matches what the OpenAI API doc says and that
validators reject the right combinations.
"""

from __future__ import annotations

import pytest

from photo_mcp import models as m


# -----------------------------------------------------------------------------
# Matrix completeness
# -----------------------------------------------------------------------------


def test_all_models_have_capabilities() -> None:
    for model in m.ALL_MODELS:
        cap = m.capability_for(model)
        assert cap.model == model


def test_known_models_match_literal_alias() -> None:
    expected = {"gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5", "gpt-image-2"}
    assert set(m.ALL_MODELS) == expected


def test_is_known_model_filters_correctly() -> None:
    assert m.is_known_model("gpt-image-1.5")
    assert m.is_known_model("gpt-image-2")
    assert not m.is_known_model("dall-e-3")
    assert not m.is_known_model("")
    assert not m.is_known_model("gpt-image-3")


# -----------------------------------------------------------------------------
# Per-model capability checks (these encode the OpenAI API as of 2026-04-25)
# -----------------------------------------------------------------------------


def test_gpt_image_2_supports_4k_sizes() -> None:
    cap = m.capability_for("gpt-image-2")
    assert "3840x2160" in cap.allowed_sizes
    assert "2160x3840" in cap.allowed_sizes
    assert "2048x2048" in cap.allowed_sizes


def test_gpt_image_1_does_not_support_4k() -> None:
    cap = m.capability_for("gpt-image-1")
    assert "3840x2160" not in cap.allowed_sizes
    assert "2048x2048" not in cap.allowed_sizes


def test_gpt_image_2_does_not_support_transparent_background() -> None:
    cap = m.capability_for("gpt-image-2")
    assert "transparent" not in cap.allowed_backgrounds
    assert "opaque" in cap.allowed_backgrounds
    assert "auto" in cap.allowed_backgrounds


def test_gpt_image_1x_supports_transparent_background() -> None:
    for model in ("gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5"):
        assert "transparent" in m.capability_for(model).allowed_backgrounds


def test_gpt_image_2_does_not_support_input_fidelity() -> None:
    assert m.capability_for("gpt-image-2").supports_input_fidelity is False


def test_gpt_image_1x_supports_input_fidelity() -> None:
    for model in ("gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5"):
        assert m.capability_for(model).supports_input_fidelity is True


@pytest.mark.parametrize("model", m.ALL_MODELS)
def test_all_models_cap_input_images_at_16(model: m.ModelId) -> None:
    assert m.capability_for(model).max_input_images == 16


@pytest.mark.parametrize("model", m.ALL_MODELS)
def test_all_models_cap_input_bytes_at_50mb(model: m.ModelId) -> None:
    assert m.capability_for(model).max_input_image_bytes == 50 * 1024 * 1024


@pytest.mark.parametrize("model", m.ALL_MODELS)
def test_all_models_cap_prompt_at_32k(model: m.ModelId) -> None:
    assert m.capability_for(model).max_prompt_chars == 32_000


# -----------------------------------------------------------------------------
# Validators
# -----------------------------------------------------------------------------


def test_validate_size_accepts_valid_size() -> None:
    assert m.validate_size("gpt-image-2", "1024x1024") is None
    assert m.validate_size("gpt-image-2", "3840x2160") is None
    assert m.validate_size("gpt-image-1", "1024x1024") is None


def test_validate_size_rejects_4k_on_gpt_image_1() -> None:
    err = m.validate_size("gpt-image-1", "3840x2160")
    assert err is not None
    assert err.parameter == "size"
    assert err.model == "gpt-image-1"
    assert "gpt-image-2" in err.supported_models
    assert "3840x2160" in err.hint or "Valid sizes" in err.hint


def test_validate_size_rejects_unknown_size() -> None:
    err = m.validate_size("gpt-image-2", "9999x9999")
    assert err is not None
    assert err.supported_models == ()  # nothing supports this size


def test_validate_background_rejects_transparent_on_gpt_image_2() -> None:
    err = m.validate_background("gpt-image-2", "transparent")
    assert err is not None
    assert err.parameter == "background"
    assert err.model == "gpt-image-2"
    # Hint must explain the substitute models the photographer can use.
    assert "gpt-image-1" in err.hint or "transparency" in err.hint
    # All 1.x models must be listed as supporting transparent
    assert {"gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5"}.issubset(set(err.supported_models))


def test_validate_background_accepts_transparent_on_gpt_image_1x() -> None:
    for model in ("gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5"):
        assert m.validate_background(model, "transparent") is None


def test_validate_input_fidelity_accepts_high_universally() -> None:
    # high is always OK — even on gpt-image-2 which forces high anyway.
    for model in m.ALL_MODELS:
        assert m.validate_input_fidelity(model, "high") is None


def test_validate_input_fidelity_rejects_low_on_gpt_image_2() -> None:
    err = m.validate_input_fidelity("gpt-image-2", "low")
    assert err is not None
    assert err.parameter == "input_fidelity"
    assert err.model == "gpt-image-2"
    # Supported models must be the three 1.x variants
    assert set(err.supported_models) == {"gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5"}


def test_validate_input_fidelity_accepts_low_on_gpt_image_1x() -> None:
    for model in ("gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5"):
        assert m.validate_input_fidelity(model, "low") is None


# -----------------------------------------------------------------------------
# UnsupportedParameter formatting
# -----------------------------------------------------------------------------


def test_unsupported_parameter_message_is_informative() -> None:
    err = m.validate_background("gpt-image-2", "transparent")
    assert err is not None
    msg = err.to_message()
    assert "background" in msg
    assert "transparent" in msg
    assert "gpt-image-2" in msg


# -----------------------------------------------------------------------------
# Frozen dataclass — capability matrix is immutable at runtime
# -----------------------------------------------------------------------------


def test_capability_record_is_frozen() -> None:
    cap = m.capability_for("gpt-image-2")
    with pytest.raises((AttributeError, Exception)):
        cap.supports_input_fidelity = True  # type: ignore[misc]


def test_all_capabilities_returns_release_order() -> None:
    caps = m.all_capabilities()
    ids = [c.model for c in caps]
    assert ids == ["gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5", "gpt-image-2"]
