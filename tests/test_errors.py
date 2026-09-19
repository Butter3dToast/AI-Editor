"""Errors, and the manual entries that must accompany them.

Spec section 14.4: a phase is not done until the troubleshooting entries are
updated for every feature in that phase. Rather than trusting that to
discipline, the last test here fails the build if an error code is missing from
the manual.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.errors import ALL_ERRORS, AIEditorError, JobFailed, LowDiskSpace

MANUAL = Path(__file__).resolve().parent.parent / "docs" / "user-manual.md"


def test_user_message_reads_as_plain_sentences():
    message = LowDiskSpace("only 2 GB free on F:").user_message()
    assert message.startswith("There is not enough free space")
    assert "only 2 GB free on F:" in message
    assert "What to do:" in message
    assert message.endswith(".")


def test_user_message_carries_the_help_code():
    assert "code E004" in LowDiskSpace().user_message()


def test_no_jargon_leaks_into_user_messages():
    """Spec section 14.2: no raw technical detail in what the creator reads."""
    banned = ("Traceback", "Exception", "None", "null", "stderr", "__")
    for error_class in ALL_ERRORS:
        message = error_class().user_message()
        for word in banned:
            assert word not in message, f"{error_class.__name__} leaks {word!r}"


def test_every_error_is_usable_without_detail():
    for error_class in ALL_ERRORS:
        assert error_class().user_message()


def test_codes_are_unique():
    codes = [e.code for e in ALL_ERRORS]
    assert len(codes) == len(set(codes)), "two errors share a code"


def test_errors_are_catchable_as_one_type():
    with pytest.raises(AIEditorError):
        raise JobFailed("transcription step")


def test_every_error_code_is_documented_in_the_manual():
    """The check that stops the manual drifting away from the software."""
    assert MANUAL.exists(), f"user manual missing at {MANUAL}"
    text = MANUAL.read_text(encoding="utf-8")
    undocumented = [
        f"{e.code} ({e.__name__})" for e in ALL_ERRORS if f"**{e.code}**" not in text
    ]
    assert not undocumented, (
        "These error codes have no entry in manual chapter 25: "
        + ", ".join(undocumented)
    )
