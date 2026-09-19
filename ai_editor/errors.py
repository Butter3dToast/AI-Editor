"""Plain-language errors.

Spec section 14.2 requires that the creator never sees a raw stack trace: every
error tells them what went wrong, why, and what to do, with a pointer to the
matching troubleshooting entry in the manual.

Every AIEditorError carries a stable ``code`` that doubles as the anchor in
docs/user-manual.md chapter 25, so the manual and the app can never drift apart
silently -- tests/test_errors.py checks that every code is documented.
"""

from __future__ import annotations


class AIEditorError(Exception):
    """Base class for every error we are willing to show the creator.

    Anything that escapes as a bare Exception is a bug: it gets logged with its
    traceback and shown as a generic "something went wrong" message.
    """

    code: str = "E000"
    what: str = "Something went wrong."
    why: str = ""
    fix: str = ""

    def __init__(self, detail: str = "", **context: object) -> None:
        self.detail = detail
        self.context = context
        super().__init__(self.user_message())

    def user_message(self) -> str:
        """The message a non-technical creator reads. No jargon, no traceback."""
        parts = [self.what]
        if self.why:
            parts.append(self.why)
        if self.detail:
            parts.append(self.detail)
        if self.fix:
            parts.append(f"What to do: {self.fix}")
        parts.append(f"(Help: manual chapter 25, code {self.code})")
        return " ".join(p.rstrip(".") + "." for p in parts if p)


# --- Setup and environment -------------------------------------------------


class FFmpegNotFound(AIEditorError):
    code = "E001"
    what = "AI-Editor could not find FFmpeg"
    why = "FFmpeg is the tool that reads and writes your video files"
    fix = (
        "If you have just installed FFmpeg, close this window and open a new one, "
        "because Windows only tells new windows where it is. Otherwise install "
        "FFmpeg, or set its folder as tools.ffmpeg_dir in Settings"
    )


class NvencNotAvailable(AIEditorError):
    code = "E002"
    what = "Your graphics card's video encoder (NVENC) is not available"
    why = "NVENC is what makes rendering fast"
    fix = "Update your NVIDIA drivers and restart, then run the setup check again"


class FolderNotWritable(AIEditorError):
    code = "E003"
    what = "AI-Editor cannot write to one of its folders"
    why = "Each folder holds working files, so it must be writable"
    fix = "Check the folder still exists and that the drive is connected, or pick a different folder in Settings"


class LowDiskSpace(AIEditorError):
    code = "E004"
    what = "There is not enough free space to start this job"
    why = "A 2-hour recording plus its working files can need tens of gigabytes"
    fix = "Free some space, or clean up finished projects under Storage"


class SettingsInvalid(AIEditorError):
    code = "E005"
    what = "A setting has a value AI-Editor cannot use"
    why = "Settings are checked when the app starts so problems surface early"
    fix = "Correct the value in Settings, or delete config/settings.yaml to return to the defaults"


# --- Media -----------------------------------------------------------------


class MediaFileNotFound(AIEditorError):
    code = "E010"
    what = "AI-Editor cannot find that video file"
    why = "The file may have been moved, renamed, or its drive disconnected"
    fix = "Open the project and click Relink media to point at the new location"


class MediaUnreadable(AIEditorError):
    code = "E011"
    what = "AI-Editor could not read that video file"
    why = "The file may be incomplete, still recording, or in an unsupported format"
    fix = "Make sure OBS has finished writing the file, then try importing it again"


class NoAudioTrack(AIEditorError):
    code = "E012"
    what = "That recording has no audio"
    why = "AI-Editor needs sound to find moments, transcribe speech, and place cuts"
    fix = "Check your OBS audio settings (manual chapter 7) and record again"


# --- Jobs ------------------------------------------------------------------


class JobFailed(AIEditorError):
    code = "E020"
    what = "A job could not finish"
    why = "The step that failed is named below; earlier finished steps were kept"
    fix = "Open the Queue and press Resume to retry from where it stopped"


ALL_ERRORS: tuple[type[AIEditorError], ...] = (
    FFmpegNotFound,
    NvencNotAvailable,
    FolderNotWritable,
    LowDiskSpace,
    SettingsInvalid,
    MediaFileNotFound,
    MediaUnreadable,
    NoAudioTrack,
    JobFailed,
)
