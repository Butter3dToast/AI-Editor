"""Settings loading and validation."""

from __future__ import annotations

import textwrap

import pytest

from ai_editor.config import DEFAULT_SETTINGS_PATH, load_settings
from ai_editor.errors import SettingsInvalid


def test_shipped_settings_load():
    """The settings.yaml we ship must validate."""
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    assert settings.folders.raw.name == "raw"
    assert settings.source_path == DEFAULT_SETTINGS_PATH


def test_shipped_defaults_match_the_spec():
    """Spec section 7.6 and manual chapter 15.2 fix these Let's Play defaults."""
    lp = load_settings(DEFAULT_SETTINGS_PATH).lets_play
    assert lp.mode == "split"
    assert lp.target_min == 30
    assert lp.normal_range_min == (25, 35)
    assert lp.story_extension_preferred_max_min == 45
    assert lp.story_extension_hard_max_min == 60
    assert lp.trim_level == "light"
    assert lp.leftover.min_standalone_min == 15
    assert lp.leftover.default_action == "carry_to_next_session"


def test_highlights_and_shorts_defaults():
    """Manual chapters 16.2 and 17.2."""
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    assert settings.highlights.target_length_min == 10
    assert settings.highlights.min_clip_score == 0.6
    assert settings.highlights.ordering == "balanced"
    assert settings.shorts.min_length_sec == 15
    assert settings.shorts.max_length_sec == 60
    assert settings.shorts.platform == "universal"


def test_render_and_storage_defaults():
    """Manual chapter 24."""
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    assert settings.render.encoder == "h264_nvenc"
    assert settings.render.loudness_target_lufs == -14.0
    assert settings.storage.low_space_warning_gb == 100
    assert settings.performance.proxy_resolution == 540
    assert settings.performance.unload_models_between_steps is True


def test_vertical_presets_are_1080x1920():
    """Spec section 7.6 Recipe C: one master format serves all three platforms."""
    presets = load_settings(DEFAULT_SETTINGS_PATH).render.presets
    for name in ("vertical_1080x1920_60", "vertical_1080x1920_30"):
        assert presets[name].width == 1080
        assert presets[name].height == 1920


def _write(tmp_path, body: str):
    path = tmp_path / "settings.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


BASE_FOLDERS = """
    folders:
      raw: {root}/raw
      cache: {root}/cache
      output: {root}/output
      assets: {root}/assets
      models: {root}/models
"""


def test_missing_file_is_readable(tmp_path):
    with pytest.raises(SettingsInvalid) as excinfo:
        load_settings(tmp_path / "nope.yaml")
    assert "settings" in excinfo.value.user_message().lower()


def test_broken_yaml_is_readable(tmp_path):
    path = _write(tmp_path, "folders: [oh no\n")
    with pytest.raises(SettingsInvalid):
        load_settings(path)


def test_target_outside_normal_range_is_rejected(tmp_path):
    """A 30-minute target with a 40-50 range is contradictory; say so early."""
    path = _write(
        tmp_path,
        BASE_FOLDERS.format(root=tmp_path.as_posix())
        + """
    lets_play:
      target_min: 30
      normal_range_min: [40, 50]
    """,
    )
    with pytest.raises(SettingsInvalid) as excinfo:
        load_settings(path)
    assert "target_min" in excinfo.value.user_message()


def test_hard_cap_below_preferred_cap_is_rejected(tmp_path):
    path = _write(
        tmp_path,
        BASE_FOLDERS.format(root=tmp_path.as_posix())
        + """
    lets_play:
      story_extension_preferred_max_min: 60
      story_extension_hard_max_min: 45
    """,
    )
    with pytest.raises(SettingsInvalid):
        load_settings(path)


def test_shorts_min_above_max_is_rejected(tmp_path):
    path = _write(
        tmp_path,
        BASE_FOLDERS.format(root=tmp_path.as_posix())
        + """
    shorts:
      min_length_sec: 90
      max_length_sec: 60
    """,
    )
    with pytest.raises(SettingsInvalid):
        load_settings(path)


def test_bad_overnight_time_is_rejected(tmp_path):
    path = _write(
        tmp_path,
        BASE_FOLDERS.format(root=tmp_path.as_posix())
        + """
    queue:
      overnight_start_time: "25:99"
    """,
    )
    with pytest.raises(SettingsInvalid):
        load_settings(path)


def test_db_and_log_paths_sit_under_cache(tmp_path):
    path = _write(tmp_path, BASE_FOLDERS.format(root=tmp_path.as_posix()))
    settings = load_settings(path)
    assert settings.db_path.parent == settings.folders.cache
    assert settings.log_dir.parent == settings.folders.cache
