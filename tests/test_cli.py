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
            "library", "analyze", "moments", "setup-obs", "companion", "sessions", "score", "clips", "highlights",
            "letsplay", "approve", "plans", "render", "export"]


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


def test_a_time_in_the_video_finds_its_clip_and_recording_time(tmp_path):
    from ai_editor.cli import _moment_in, _seconds
    from ai_editor.config import Settings
    from ai_editor.recipes.plan import EditPlan, Segment

    assert _seconds("6:36") == 396 and _seconds("1:02:03") == 3723 and _seconds("x") is None
    settings = Settings(folders={k: tmp_path for k in ("raw", "cache", "output", "assets", "models")})
    plan = EditPlan("p", "highlights", "T", None, 600,
                    [Segment(9, 7600.0, 7612.0, kind="teaser", clip_id="a"),
                     Segment(9, 7893.0, 7945.0, clip_id="b")])
    assert _moment_in(plan, "0:20-0:26", settings) == ("b", (7901.0, 7907.0))
    assert _moment_in(plan, "0:05", settings) == ("a", (7605.0, 7605.0))
    assert _moment_in(plan, "0:10-0:20", settings) is None  # runs from one clip into the next
