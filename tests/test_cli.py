"""The command line: every command at least loads and explains itself.

Added after a syntax error in cli.py slipped past the whole suite, because no
other test imports the command-line module.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from ai_editor.cli import app

runner = CliRunner()

COMMANDS = ["version", "doctor", "init-db", "probe", "import", "import-twitch", "attach-chat",
            "library", "analyze", "moments", "setup-obs", "companion", "sessions", "score", "clips"]


def test_top_level_help_lists_every_command():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in COMMANDS:
        assert command in result.output


@pytest.mark.parametrize("command", COMMANDS)
def test_each_command_has_help(command):
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0, result.output


def test_library_on_an_empty_library(settings):
    result = runner.invoke(app, ["library", "--settings", str(settings.source_path)])
    assert result.exit_code == 0
    assert "empty" in result.output


def test_sessions_before_any_exist(settings):
    result = runner.invoke(app, ["sessions", "--settings", str(settings.source_path)])
    assert result.exit_code == 0
    assert "No sessions yet" in result.output


def test_moments_for_a_missing_recording_is_a_readable_error(settings):
    result = runner.invoke(app, ["moments", "7", "--settings", str(settings.source_path)])
    assert result.exit_code == 1
    assert "E015" in result.output
    assert "Traceback" not in result.output
