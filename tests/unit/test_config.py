"""Configuration loading and resolution-order tests.

Verifies the documented resolution order: defaults → TOML → env. Each
later layer overrides the previous; CLI / per-call args are tested at
the boundaries that consume them, not here.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from photo_mcp import config as cfg_mod


# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------


def test_defaults_match_constants() -> None:
    c = cfg_mod.Config()
    assert c.default_generate_model == cfg_mod.DEFAULT_GENERATE_MODEL
    assert c.default_edit_model == cfg_mod.DEFAULT_EDIT_MODEL
    assert c.default_output_format == cfg_mod.DEFAULT_OUTPUT_FORMAT
    assert c.default_quality == cfg_mod.DEFAULT_QUALITY
    assert c.session_cost_ceiling_usd == 0.0
    assert c.follow_symlinks is False
    assert c.transport == "stdio"


# -----------------------------------------------------------------------------
# require_api_key
# -----------------------------------------------------------------------------


def test_require_api_key_raises_on_empty() -> None:
    c = cfg_mod.Config(api_key="")
    with pytest.raises(cfg_mod.MissingApiKey):
        cfg_mod.require_api_key(c)


def test_require_api_key_returns_value() -> None:
    c = cfg_mod.Config(api_key="sk-test-only-not-real")
    assert cfg_mod.require_api_key(c) == "sk-test-only-not-real"


# -----------------------------------------------------------------------------
# Env-variable resolution
# -----------------------------------------------------------------------------


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every PHOTO_MCP_* and OPENAI_API_KEY var before each test."""
    for k in list(os.environ):
        if k.startswith("PHOTO_MCP_") or k == "OPENAI_API_KEY":
            monkeypatch.delenv(k, raising=False)


def test_env_overrides_log_level(clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PHOTO_MCP_LOG_LEVEL", "debug")
    c = cfg_mod.load(config_path=tmp_path / "missing.toml")
    assert c.log_level == "debug"


def test_env_overrides_cost_ceiling(clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PHOTO_MCP_COST_CEILING_USD", "12.5")
    c = cfg_mod.load(config_path=tmp_path / "missing.toml")
    assert c.session_cost_ceiling_usd == pytest.approx(12.5)


def test_env_invalid_cost_ceiling_keeps_default(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PHOTO_MCP_COST_CEILING_USD", "not-a-number")
    c = cfg_mod.load(config_path=tmp_path / "missing.toml")
    assert c.session_cost_ceiling_usd == 0.0


def test_env_loads_api_key(clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-only-not-real")
    c = cfg_mod.load(config_path=tmp_path / "missing.toml")
    assert c.api_key == "sk-test-only-not-real"


def test_env_follow_symlinks_truthy(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for val in ("true", "1", "yes", "on", "TRUE"):
        monkeypatch.setenv("PHOTO_MCP_FOLLOW_SYMLINKS", val)
        c = cfg_mod.load(config_path=tmp_path / "missing.toml")
        assert c.follow_symlinks is True, f"failed for {val!r}"


def test_env_follow_symlinks_falsy(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for val in ("false", "0", "no", "off", "FALSE"):
        monkeypatch.setenv("PHOTO_MCP_FOLLOW_SYMLINKS", val)
        c = cfg_mod.load(config_path=tmp_path / "missing.toml")
        assert c.follow_symlinks is False, f"failed for {val!r}"


def test_env_allowed_input_roots_pathsep_split(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    a = tmp_path / "a"
    a.mkdir()
    b = tmp_path / "b"
    b.mkdir()
    monkeypatch.setenv("PHOTO_MCP_ALLOWED_INPUT_ROOTS", f"{a}{os.pathsep}{b}")
    c = cfg_mod.load(config_path=tmp_path / "missing.toml")
    assert set(c.allowed_input_roots) == {a.resolve(), b.resolve()}


# -----------------------------------------------------------------------------
# TOML resolution
# -----------------------------------------------------------------------------


def test_toml_overrides_defaults(clean_env: None, tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        'default_generate_model = "gpt-image-1"\n'
        'default_edit_model = "gpt-image-1.5"\n'
        'session_cost_ceiling_usd = 5.0\n'
        'log_level = "warning"\n',
        encoding="utf-8",
    )
    c = cfg_mod.load(config_path=toml)
    assert c.default_generate_model == "gpt-image-1"
    assert c.default_edit_model == "gpt-image-1.5"
    assert c.session_cost_ceiling_usd == 5.0
    assert c.log_level == "warning"


def test_env_overrides_toml(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text('log_level = "warning"\n', encoding="utf-8")
    monkeypatch.setenv("PHOTO_MCP_LOG_LEVEL", "debug")
    c = cfg_mod.load(config_path=toml)
    assert c.log_level == "debug"


def test_malformed_toml_raises(clean_env: None, tmp_path: Path) -> None:
    toml = tmp_path / "broken.toml"
    toml.write_text("this is = not valid =\ntoml [unterminated\n", encoding="utf-8")
    with pytest.raises(cfg_mod.ConfigError):
        cfg_mod.load(config_path=toml)


def test_missing_toml_is_silent_default(clean_env: None, tmp_path: Path) -> None:
    c = cfg_mod.load(config_path=tmp_path / "nope.toml")
    assert c.default_generate_model == cfg_mod.DEFAULT_GENERATE_MODEL


def test_toml_unknown_keys_ignored(clean_env: None, tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        'default_generate_model = "gpt-image-1"\n'
        'unknown_field = "ignored"\n'
        'future_v2_setting = 42\n',
        encoding="utf-8",
    )
    c = cfg_mod.load(config_path=toml)
    assert c.default_generate_model == "gpt-image-1"


# -----------------------------------------------------------------------------
# path_policy() derivation
# -----------------------------------------------------------------------------


def test_path_policy_falls_back_to_home_when_unconfigured() -> None:
    c = cfg_mod.Config()
    pol = c.path_policy()
    # When allowed_input_roots is empty, the policy uses Path.home() at
    # canonicalize time. Verify the policy carries empty tuples (the
    # fallback happens deeper).
    assert pol.allowed_input_roots == ()
    assert pol.allowed_output_roots == ()
    assert pol.follow_symlinks is False


def test_path_policy_propagates_explicit_roots(tmp_path: Path) -> None:
    c = cfg_mod.Config(
        allowed_input_roots=(tmp_path,),
        allowed_output_roots=(tmp_path,),
        follow_symlinks=True,
    )
    pol = c.path_policy()
    assert pol.allowed_input_roots == (tmp_path,)
    assert pol.allowed_output_roots == (tmp_path,)
    assert pol.follow_symlinks is True
