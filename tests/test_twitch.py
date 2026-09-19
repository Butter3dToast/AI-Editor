"""Twitch links, VOD information, and chat files.

The fixtures in tests/data are real replies from Twitch for the creator's
public VOD 2875855539, so these tests check the format Twitch actually sends.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_editor import twitch
from ai_editor.errors import InvalidVodLink

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize(
    "link",
    [
        "2875855539",
        "https://www.twitch.tv/videos/2875855539",
        "https://www.twitch.tv/videos/2875855539?t=1h2m3s",
        "https://dashboard.twitch.tv/u/butter3dtoast/content/video-producer/edit/2875855539",
        '  "https://www.twitch.tv/videos/2875855539"  ',
    ],
)
def test_vod_number_from_any_link(link):
    assert twitch.parse_vod_id(link) == "2875855539"


@pytest.mark.parametrize("bad", ["", "hello", "https://www.twitch.tv/butter3dtoast", "123"])
def test_not_a_vod_link(bad):
    with pytest.raises(InvalidVodLink):
        twitch.parse_vod_id(bad)


def test_real_vod_information_is_read():
    raw = (DATA / "twitch_info_2875855539.txt").read_text(encoding="utf-8")
    info = twitch.parse_info(raw, "2875855539")
    assert info.title == "[DROPS] Its Doggy Time"
    assert info.channel == "Butter3dToast"
    assert info.game == "WARDOGS"
    assert info.length_sec == 11887
    assert info.created_at == datetime(2026, 9, 16, 17, 55, 7, tzinfo=timezone.utc)


def _info(days_old):
    return twitch.VodInfo("1", "t", "c", datetime.now(timezone.utc) - timedelta(days=days_old), 60.0)


def test_no_warning_for_a_fresh_vod():
    assert twitch.expiry_warning(_info(2), keep_days=14) is None


def test_warning_when_deletion_is_close():
    warning = twitch.expiry_warning(_info(12), keep_days=14)
    assert warning and "2 day" in warning


def test_warning_when_past_the_keep_time():
    assert "may already be deleting" in twitch.expiry_warning(_info(20), keep_days=14)


def test_real_chat_file_is_read():
    messages = twitch.load_chat(DATA / "twitch_chat_2875855539.json")
    assert len(messages) == 1
    assert messages[0].t_sec == 11
    assert messages[0].username == "StreamElements"
    assert messages[0].text.startswith("Butter3dToast is now live!")


def test_chat_is_sorted_and_skips_broken_comments(tmp_path):
    path = tmp_path / "chat.json"
    path.write_text(json.dumps({"comments": [
        {"content_offset_seconds": 30, "commenter": {"display_name": "b"}, "message": {"body": "later"}},
        {"commenter": {"display_name": "x"}, "message": {"body": "no time"}},
        {"content_offset_seconds": 5.5, "commenter": {"display_name": "a"}, "message": {"body": "first"}},
    ]}), encoding="utf-8")
    assert [m.text for m in twitch.load_chat(path)] == ["first", "later"]


def test_tool_folder_defaults_beside_the_models_folder(settings):
    assert twitch.tools_folder(settings) == settings.folders.models.parent / "tools"


def test_errors_from_the_tool_become_plain_language(settings, monkeypatch, tmp_path):
    """A private VOD reads as 'deleted/expired' to Twitch; the creator sees E041."""
    fake = tmp_path / "fake.cmd"
    fake.write_text("@echo Invalid VOD, deleted/expired VOD possibly?\n@exit /b 1\n")
    monkeypatch.setattr(twitch, "cli_path", lambda _s: fake)
    with pytest.raises(twitch.VodNotAvailable) as excinfo:
        twitch.vod_info(settings, "2874991382")
    assert "Video Producer" in excinfo.value.user_message()


def test_progress_moves_forward_through_the_download_stages():
    """Real output: each of the four stages counts 0-100% on its own."""
    lines = [
        "[STATUS] - Fetching Video Info [1/4]",
        "[STATUS] - Downloading 0% [2/4]",
        "[STATUS] - Downloading 100% [2/4]",
        "[STATUS] - Verifying Parts 50% [3/4]",
        "[STATUS] - Finalizing Video 0% [4/4] ",
        "[STATUS] - Finalizing Video 100% [4/4]",
    ]
    values = [v for v in (twitch.progress_from_line(line) for line in lines) if v is not None]
    assert values == [0.25, 0.5, 0.625, 0.75, 1.0]
    assert values == sorted(values), "never jumps backwards"


def test_progress_without_stages():
    assert twitch.progress_from_line("[STATUS] - Downloading 40%") == 0.4
    assert twitch.progress_from_line("[STATUS] - Writing Output File") is None


def test_empty_answer_means_the_vod_is_not_public():
    """Real behaviour: for a private VOD, Twitch answers with "video": null."""
    raw = '[STATUS] - Fetching Video Info [1/1]\n{"data":{"video":null},"extensions":{}}\n'
    with pytest.raises(twitch.VodNotAvailable):
        twitch.parse_info(raw, "2874991382")
