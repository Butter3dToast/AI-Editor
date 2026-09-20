"""Private settings (the OBS password) stay in a file git never sees."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ai_editor.config import load_settings, local_settings_path, save_local_setting

ROOT = Path(__file__).resolve().parent.parent


def test_local_file_overrides_only_what_it_names(settings):
    path = settings.source_path
    save_local_setting(path, "obs", "websocket_password", "hunter2")
    reloaded = load_settings(path)
    assert reloaded.obs.websocket_password == "hunter2"
    assert reloaded.obs.websocket_port == 4455  # untouched
    assert reloaded.folders == settings.folders


def test_saving_keeps_other_local_values(settings):
    path = settings.source_path
    save_local_setting(path, "obs", "websocket_port", 4460)
    save_local_setting(path, "obs", "websocket_password", "pw")
    reloaded = load_settings(path)
    assert (reloaded.obs.websocket_port, reloaded.obs.websocket_password) == (4460, "pw")


def test_local_file_sits_beside_settings():
    assert local_settings_path(Path("config/settings.yaml")) == Path("config/settings.local.yaml")


def test_git_ignores_the_real_local_file():
    result = subprocess.run(
        ["git", "check-ignore", "-q", "config/settings.local.yaml"], cwd=ROOT, capture_output=True
    )
    assert result.returncode == 0, "config/settings.local.yaml must be listed in .gitignore"
