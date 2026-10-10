"""Settings loading and validation.

config/settings.yaml is the single source of truth for folders, model choices,
recipe defaults, and render presets. Every value is mirrored in the manual's
settings reference (chapter 24).

Validation happens at startup rather than deep inside a two-hour render, so a
typo surfaces as a plain-language message before any work begins.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .errors import SettingsInvalid

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"


class Folders(BaseModel):
    raw: Path
    cache: Path
    output: Path
    assets: Path
    models: Path

    def all(self) -> dict[str, Path]:
        return {name: getattr(self, name) for name in type(self).model_fields}


class Tools(BaseModel):
    """Explicit locations for external programs.

    Left empty, AI-Editor finds them itself. This exists so the "set its
    location in Settings" advice in error E001 is actually possible.
    """

    ffmpeg_dir: Path | None = None
    folder: Path | None = None


class Performance(BaseModel):
    device: Literal["gpu", "cpu"] = "gpu"
    unload_models_between_steps: bool = True
    proxy_resolution: int = Field(540, ge=180, le=1080)
    proxy_fps: int = Field(30, ge=10, le=60)
    ffmpeg_threads: int = Field(0, ge=0, le=64)


class Queue(BaseModel):
    overnight_start_time: str | None = None
    shutdown_when_finished: bool = False

    @field_validator("overnight_start_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        hh, _, mm = v.partition(":")
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60):
            raise ValueError(f"overnight_start_time must look like '02:00', got {v!r}")
        return v


class Companion(BaseModel):
    # Who catches the marker keys. "obs": you bind them in OBS's hotkey
    # settings (manual 7.4a), which keeps working inside games that switch
    # other programs' hotkeys off, as League does. "windows": the Companion
    # reserves the two keys below itself.
    marker_keys: Literal["obs", "windows"] = "obs"
    mark_moment_hotkey: str = "numpad+"
    mark_short_hotkey: str = "numpad-"
    # Off: on 26 Sep the click reached the stream through the creator's stand-up
    # mic, which the Desktop Audio check in companion/sound.py can't see.
    confirmation_sound: bool = False
    sound_volume: float = Field(0.9, ge=0.05, le=1.0)
    start_with_windows: bool = False
    # Which game each OBS scene shows, for scenes whose name doesn't say it.
    # A scene named after its game ("Wardogs", "Tarkov Main") needs no entry.
    scene_games: dict[str, str] = Field(default_factory=dict)


class Obs(BaseModel):
    websocket_host: str = "127.0.0.1"
    websocket_port: int = Field(4455, ge=1, le=65535)
    websocket_password: str = ""


class Analysis(BaseModel):
    transcription_model: str = "large-v3"
    compute_type: str = "float16"
    voice_separation: Literal["vods", "mixed", "off"] = "vods"
    signal_rate_hz: int = Field(1, ge=1, le=10)
    language: str = "en"
    # Names the speech recognition doesn't know come out as ordinary words
    # that sound the same; these put them right afterwards (heard -> meant).
    # Telling Whisper the names beforehand was tried and dropped: every
    # version of it made Whisper "hear" words nobody said (see
    # transcript.fix_spellings).
    spellings: dict[str, str] = Field(default_factory=lambda: {
        "talk of": "Tarkov", "tarkoff": "Tarkov", "war dogs": "Wardogs", "war dog's": "Wardogs"})
    voice_detector: Literal["auto", "on", "off"] = "auto"
    silence_threshold_db: float = Field(-50.0, ge=-90.0, le=-10.0)
    event_window_sec: float = Field(2.0, ge=1.0, le=10.0)
    # How different a frame must look from the ones around it to count as a cut.
    scene_threshold: float = Field(5.0, ge=1.0, le=20.0)


class Scoring(BaseModel):
    """How the per-second signals add up into one "how good is this moment" score.

    Every weight is documented in manual chapter 24. Markers dominate on
    purpose (spec section 7.3: "the creator's own picks; very high weight").
    """

    weights: dict[str, float] = Field(default_factory=lambda: {
        "marker": 4.0,
        "marker_short": 4.0,
        # Funny beats loud: on the creator's Wardogs stream, the moment that
        # won on loudness alone was ordinary, and the two they picked out as
        # best were the ones with laughter in them.
        "laughter": 2.5,
        "scream": 1.2,
        "shout": 1.0,
        "explosion": 0.9,
        "gunfire": 0.8,
        "chat_z": 1.2,
        "energy_z": 0.5,
        "speech": 0.2,
        "silence": -0.5,
    })
    # Sounds that only mean something when they keep going. A single shot is
    # someone testing their gun; fifteen seconds of it is a firefight. Each
    # named signal is averaged over this many seconds before it counts.
    sustain_sec: dict[str, float] = Field(default_factory=lambda: {
        "gunfire": 15.0,
        "explosion": 10.0,
    })
    # Added for each extra kind of thing happening at once. Every Wardogs clip
    # the creator liked was a fight *and* them reacting; every one they
    # rejected was only one of the two (see hype.combination_bonus).
    combination_bonus: float = Field(1.2, ge=0.0, le=5.0)
    # How strong a signal must be to count as one of those kinds. Low on
    # purpose: the sound model hears laughter faintly.
    combination_threshold: float = Field(0.1, ge=0.0, le=1.0)
    # A marker is pressed after the good bit, so it counts backwards from the press.
    marker_lookback_sec: float = Field(60.0, ge=1.0, le=300.0)
    marker_lookahead_sec: float = Field(10.0, ge=0.0, le=120.0)
    # Peaks are judged on a few seconds together, not one loud second.
    smooth_sec: float = Field(5.0, ge=1.0, le=60.0)
    # Loudness and chat are z-scores; this is what counts as "as high as it gets".
    zscore_full_scale: float = Field(3.0, gt=0.0)
    # A picture this dark (0 black - 255 white) counts as a black screen: it is
    # never a moment, and clips don't start or end on one. Video black is 16.
    dark_level: float = Field(24.0, ge=0.0, le=128.0)
    # ...for at least this many seconds in a row: a loading or setup screen.
    # Shorter ones are part of the moment: a blinking effect (one dark second
    # every 6 s on Wardogs) or a crash (5 s of black while the creator said
    # "I'm so sorry, I thought I could put it off" -- the helicopter clip).
    dark_min_sec: int = Field(10, ge=1, le=120)


class Clips(BaseModel):
    """How peaks in the score become clips with clean edges (spec section 7.3)."""

    # A moment must score at least this (1.0 = the recording's best) to become
    # a clip. 0.2 keeps enough candidates for a 10-minute highlight (Wardogs:
    # 25 clips, 13 minutes) without changing which rank first.
    min_score: float = Field(0.2, ge=0.0, le=1.0)
    # The part of a peak that stays above this share of its top is its core.
    core_fraction: float = Field(0.5, gt=0.0, lt=1.0)
    # Context before the core. Laughter comes after the funny thing (the creator:
    # "it could have happened 10 or 30 seconds before"), and the clip they liked
    # most was worth it for the 40 seconds of fight leading up to the moment.
    # Generous on purpose: recipes trim clips, but can't add back what was left out.
    lead_in_sec: float = Field(30.0, ge=0.0, le=120.0)
    # After the core, so the reaction can finish.
    tail_sec: float = Field(4.0, ge=0.0, le=60.0)
    min_length_sec: float = Field(15.0, ge=3.0, le=300.0)
    max_length_sec: float = Field(90.0, ge=10.0, le=600.0)
    # How far an edge may move to land on a clean point (a pause, the end of
    # a sentence, a scene change).
    snap_sec: float = Field(6.0, ge=0.0, le=30.0)
    # A gap in speech at least this long counts as a pause.
    pause_sec: float = Field(0.5, ge=0.1, le=5.0)
    # A clip only ends where the speaker then stays quiet at least this long.
    # A breath between sentences isn't a stop: on the creator's League stream
    # a 0.56 s gap after "Keep her alive." was followed by "I..." and then 10 s
    # of silence on the mic -- the thought ended after the "I", not before it.
    end_pause_sec: float = Field(1.0, ge=0.1, le=5.0)
    # How much longer a clip may run to reach such a pause, so it never ends
    # while the creator is mid-thought (League: "cuts off where I am talking").
    end_extend_sec: float = Field(10.0, ge=0.0, le=60.0)
    # Nor while the fight is still going. Wardogs: a clip ended with gunfire
    # still coming in bursts, and the creator: "the tool would have captured
    # me killing some people". Shooting at least fight_level, recurring within
    # fight_gap_sec, counts as the same fight, for up to fight_extend_sec more.
    fight_level: float = Field(0.2, ge=0.0, le=1.0)
    fight_gap_sec: float = Field(10.0, ge=1.0, le=60.0)
    fight_extend_sec: float = Field(30.0, ge=0.0, le=120.0)
    # A scene change only stops a clip if it stands alone: more than this
    # many others within scene_busy_window_sec either side means camera
    # editing (a cutscene), not a menu or loading screen.
    scene_busy_count: int = Field(3, ge=1, le=50)
    scene_busy_window_sec: float = Field(30.0, ge=5.0, le=300.0)

    def check_consistency(self) -> None:
        if self.min_length_sec >= self.max_length_sec:
            raise ValueError("clips.min_length_sec must be below max_length_sec")


class Leftover(BaseModel):
    min_standalone_min: float = 15.0
    default_action: Literal["carry_to_next_session", "merge_into_previous"] = (
        "carry_to_next_session"
    )


class SplitPenalties(BaseModel):
    """Costs used by the split optimiser (spec section 7.6).

    ``split_inside_cutscene_dialogue_fight`` stays the literal string
    "forbidden" because it is a hard constraint, not a weight to trade off.
    """

    per_min_outside_normal_range: float = 1.0
    per_min_over_45: float = 4.0
    split_inside_story_mission: float = 50.0
    split_inside_cutscene_dialogue_fight: str = "forbidden"


class LetsPlay(BaseModel):
    # Games recorded as Let's Play series. Their recordings are episodes, not
    # streams, so they stay out of stream highlights.
    games: list[str] = Field(default_factory=lambda: ["The Blood of Dawnwalker"])
    mode: Literal["split", "condense"] = "split"
    target_min: float = Field(30.0, gt=0)
    normal_range_min: tuple[float, float] = (25.0, 35.0)
    story_extension_preferred_max_min: float = 45.0
    story_extension_hard_max_min: float = 60.0
    trim_level: Literal["light", "standard", "tight"] = "light"
    # The always-trim pass (recipes/letsplay.py). Silence longer than this is
    # cut down, keeping dead_air_keep_sec either side. The creator chose 20 s.
    dead_air_sec: float = Field(20.0, ge=5.0, le=300.0)
    dead_air_keep_sec: float = Field(3.0, ge=0.5, le=15.0)
    # A black screen this long, with nobody talking, is a loading screen.
    loading_min_sec: int = Field(2, ge=1, le=60)
    # A picture changing less than this from one second to the next is still:
    # a menu, the map, the inventory. Cut after still_min_sec, unless talking.
    still_level: float = Field(1.0, ge=0.0, le=50.0)
    still_min_sec: int = Field(5, ge=1, le=120)
    # The game's on-screen display showing at least this much means play;
    # less, with nobody talking, is a cutscene or a choice and is never cut.
    hud_level: float = Field(0.15, ge=0.0, le=1.0)
    # Moments scoring this well (1.0 = the episode's best) are never trimmed.
    protect_score: float = Field(0.5, ge=0.0, le=1.0)
    penalties: SplitPenalties = SplitPenalties()
    bonus_hook_ending: float = -5.0
    leftover: Leftover = Leftover()
    recap_at_start: bool = False
    recap_max_sec: float = 15.0
    hook_endings: bool = True
    speedup_indicator: bool = True
    tolerance_pct: float = Field(15.0, ge=0, le=50)
    # Shown over the start of every part, e.g. "Ep {episode} – Part {part}"
    # ({episode} and {part} are filled in). Empty = none: the creator found it
    # repeats the YouTube title.
    title_card: str = ""
    title_card_sec: float = Field(4.0, ge=1.0, le=15.0)

    @field_validator("title_card")
    @classmethod
    def _title_fields(cls, v: str) -> str:
        try:
            v.format(episode=1, part=1)
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(f"title_card can use {{episode}} and {{part}} only: {exc}") from exc
        return v

    @field_validator("normal_range_min")
    @classmethod
    def _range_ordered(cls, v: tuple[float, float]) -> tuple[float, float]:
        if v[0] >= v[1]:
            raise ValueError(f"normal_range_min must be [low, high], got {list(v)}")
        return v

    def check_consistency(self) -> None:
        """Cross-field checks that pydantic can't express field by field."""
        low, high = self.normal_range_min
        if not low <= self.target_min <= high:
            raise ValueError(
                f"target_min ({self.target_min}) must sit inside normal_range_min "
                f"({low}-{high})"
            )
        if self.story_extension_preferred_max_min > self.story_extension_hard_max_min:
            raise ValueError(
                "story_extension_preferred_max_min cannot exceed "
                "story_extension_hard_max_min"
            )
        if self.story_extension_preferred_max_min < high:
            raise ValueError(
                "story_extension_preferred_max_min must be at least the top of "
                "normal_range_min"
            )


class Highlights(BaseModel):
    target_length_min: float = Field(10.0, gt=0)
    # The quality bar: nothing below it goes in to fill time. On the creator's
    # Wardogs verdicts every clip they liked scored 0.56 or more, and the
    # first one they rejected 0.54.
    min_clip_score: float = Field(0.55, ge=0.0, le=1.0)
    # Where clips come from when one stream isn't enough. oldest_first uses
    # up the earliest stream's good clips, then the next (the creator's own
    # description: "4 min from the previous and 6 min from the next");
    # best_first takes the highest-scoring clips from any stream.
    fill_order: Literal["oldest_first", "best_first"] = "oldest_first"
    # Each clip is trimmed down to its moment: this much before it, and no
    # longer than max_clip_sec overall. Library clips are generous on purpose;
    # a highlight video needs pace ("some are long winded and don't get to
    # the punchline").
    lead_in_sec: float = Field(15.0, ge=0.0, le=120.0)
    max_clip_sec: float = Field(50.0, ge=10.0, le=300.0)
    # timeline: in the order it happened, the teaser's moment saved for last (the
    # creator's own layout, 2026-10-03). balanced: strong opener, alternating
    # intensity, best last. chronological: strictly in order. best_last: rising.
    ordering: Literal["timeline", "chronological", "balanced", "best_last"] = "timeline"
    hook: bool = True
    hook_seconds: tuple[float, float] = (5.0, 15.0)
    allow_reused_clips: bool = False
    always_include_pinned: bool = True
    always_include_markers: bool = True


class SafeZone(BaseModel):
    bottom: float = Field(0.0, ge=0.0, le=0.6)
    right: float = Field(0.0, ge=0.0, le=0.6)
    top: float = Field(0.0, ge=0.0, le=0.6)


class Box(BaseModel):
    """A rectangle on the recording, as shares of its width and height (0-1)."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _inside(self) -> "Box":
        if self.x + self.w > 1.0001 or self.y + self.h > 1.0001:
            raise ValueError("a box must fit inside the picture (x + w and y + h at most 1)")
        return self


Layout = Literal["crop", "fit", "facecam_top"]


class Shorts(BaseModel):
    """Vertical clips (spec 7.6 Recipe C). The creator's choices, 2026-10-04: no
    facecam yet, so the game fills the frame -- zoomed in on the centre for
    League, Tarkov and Wardogs, the whole picture over a blurred copy for
    Dawnwalker -- switchable per Short; up to five suggested per stream; one
    file for every platform."""

    min_length_sec: float = Field(15.0, gt=0)
    max_length_sec: float = Field(60.0, gt=0)
    # Each Short opens this long before its moment: straight into the action
    # (spec: "hook in the first 1-2 seconds"), with just enough to follow it.
    lead_in_sec: float = Field(8.0, ge=0.0, le=30.0)
    tail_sec: float = Field(3.0, ge=0.0, le=20.0)
    per_recording: int = Field(5, ge=1, le=20)
    platform: Literal["youtube_shorts", "tiktok", "universal"] = "universal"
    preset: str = "vertical_1080x1920_60"
    # crop: the centre of the game, zoomed to fill the frame. fit: the whole
    # picture, a blurred copy filling above and below. facecam_top: the
    # facecam (marked in `facecam`) above, the game below.
    default_layout: Layout = "crop"
    layouts: dict[str, Layout] = Field(
        default_factory=lambda: {"The Blood of Dawnwalker": "fit"})
    # Where the crop is centred, left to right (0.5 = the middle), per game.
    crop_centre: dict[str, float] = Field(default_factory=dict)
    # How much of the frame's height the zoomed game fills; the rest is the
    # blurred copy, above and below. 1.0 fills it all. Below 1 is zoomed out:
    # at 1.0 League's health bars and ability bar were cut off at the sides
    # (the creator, 2026-10-05: "zoom out a tad").
    crop_fill: float = Field(0.75, ge=0.5, le=1.0)  # chosen 2026-10-05
    # Per game. League at 0.65: its fights spread wide (the creator, 2026-10-05).
    crop_fills: dict[str, float] = Field(
        default_factory=lambda: {"League of Legends": 0.65})
    # Where the facecam is on screen, per game. None yet: the creator has no
    # facecam. Marking one makes facecam_top that game's layout.
    facecam: dict[str, Box] = Field(default_factory=dict)
    facecam_share: float = Field(0.33, ge=0.2, le=0.5)  # of the frame's height
    captions: bool = True
    follow_action: bool = False
    hook: bool = True
    must_make_sense_alone: bool = True
    link_to_full_video: bool = True
    # Story games: titles avoid spoilers, and Shorts are flagged to check (spec 7.6).
    spoiler_check_games: list[str] = Field(
        default_factory=lambda: ["The Blood of Dawnwalker"])
    safe_zones: dict[str, SafeZone] = Field(default_factory=dict)

    @field_validator("crop_centre")
    @classmethod
    def _centres(cls, v: dict[str, float]) -> dict[str, float]:
        for game, x in v.items():
            if not 0.0 <= x <= 1.0:
                raise ValueError(f"shorts.crop_centre for {game} must be 0-1, got {x}")
        return v

    def fill_for(self, game: str | None) -> float:
        return self.crop_fills.get(game or "", self.crop_fill)

    def layout_for(self, game: str | None) -> str:
        if game and game in self.facecam:
            return "facecam_top"
        return self.layouts.get(game or "", self.default_layout)

    def safe_zone(self) -> SafeZone:
        return self.safe_zones.get(self.platform) or SafeZone(bottom=0.26, right=0.20, top=0.08)

    def check_consistency(self) -> None:
        if self.min_length_sec >= self.max_length_sec:
            raise ValueError("shorts.min_length_sec must be below max_length_sec")


class RenderPreset(BaseModel):
    width: int
    height: int
    fps: int
    bitrate: str


class CaptionPlace(BaseModel):
    highlights: float = Field(0.12, ge=0.0, le=0.8)
    lets_play: float = Field(0.22, ge=0.0, le=0.8)


class Captions(BaseModel):
    # Burned into finished videos. Off unless turned on here or per video
    # with --captions (the creator's choice: captions are an option).
    highlights: bool = False
    lets_play: bool = False
    font: str = "Arial"
    size: int = Field(64, ge=20, le=160)    # pixels on a 1080-high picture
    bold: bool = True
    outline: float = Field(4.0, ge=0, le=12)
    # How far up from the bottom the captions sit, as a share of the picture's
    # height. Higher in Let's Plays, above the game's own subtitles.
    position: CaptionPlace = CaptionPlace()
    # Shorts: a few words at a time, the one being said lit up (the creator's
    # choice, 2026-10-04), big, kept out of the platforms' buttons.
    shorts_size: int = Field(88, ge=30, le=200)   # pixels on a 1920-high picture
    shorts_words: int = Field(3, ge=1, le=6)      # words on screen at once, at most
    shorts_highlight: str = "#FFD400"             # the word being said

    @field_validator("shorts_highlight")
    @classmethod
    def _colour(cls, v: str) -> str:
        import re

        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            raise ValueError(f"captions.shorts_highlight must look like #FFD400, got {v!r}")
        return v.upper()


EffectKind = Literal["flash", "shake", "sfx"]


class Effects(BaseModel):
    """Effects on the big moments (spec 7.8), placed by AI-Editor itself.

    Which ones are on, per kind of video; each video can switch them on or
    off for itself in Review. The creator's choices: none in Let's Plays
    (2026-10-05); and off by default in highlights and Shorts too until
    League's own events place them (Phase 2E): after the 2C-1 test their
    timing "seemed random" (2026-10-10). Ticked per video in Review meanwhile.
    """

    highlights: list[EffectKind] = []
    shorts: list[EffectKind] = []
    lets_play: list[EffectKind] = []
    # Effects go on the moments the creator marked with the Stream Companion,
    # one per mark (effects/placement.py); at most this many per minute.
    highlights_per_min: float = Field(1.5, ge=0.0, le=10.0)
    shorts_per_min: float = Field(3.0, ge=0.0, le=10.0)
    lets_play_per_min: float = Field(0.75, ge=0.0, le=10.0)
    min_gap_sec: float = Field(6.0, ge=1.0)
    # Sound effects' loudness against the loud parts of the clip they're in.
    sfx_volume_db: float = Field(-3.0, ge=-30.0, le=10.0)
    # Between the clips of a highlight video: a hard cut, or the new clip
    # sliding in over the old one (render/slide.py). The creator's choice
    # (2026-10-10): hard cut, slide optional.
    between_clips: Literal["cut", "slide"] = "cut"

    @field_validator("between_clips", mode="before")
    @classmethod
    def _was_whoosh(cls, v):
        return "slide" if v == "whoosh" else v   # tried first, replaced by the slide
    flash_strength: float = Field(0.35, ge=0.05, le=1.0)    # 1: a white screen
    shake_strength: float = Field(0.02, ge=0.005, le=0.08)  # how far, as a share of the height

    def on_for(self, recipe: str) -> list[str]:
        return list({"shorts": self.shorts, "letsplay": self.lets_play}.get(recipe,
                                                                             self.highlights))

    def per_min(self, recipe: str) -> float:
        return {"shorts": self.shorts_per_min,
                "letsplay": self.lets_play_per_min}.get(recipe, self.highlights_per_min)


class Render(BaseModel):
    encoder: Literal["h264_nvenc", "hevc_nvenc"] = "h264_nvenc"
    nvenc_preset: str = "p5"
    loudness_target_lufs: float = -14.0
    presets: dict[str, RenderPreset] = Field(default_factory=lambda: {
        "youtube_1080p60": RenderPreset(width=1920, height=1080, fps=60, bitrate="16M"),
        "youtube_1080p30": RenderPreset(width=1920, height=1080, fps=30, bitrate="12M"),
        "vertical_1080x1920_60": RenderPreset(width=1080, height=1920, fps=60, bitrate="12M"),
        "vertical_1080x1920_30": RenderPreset(width=1080, height=1920, fps=30, bitrate="10M"),
    })
    # Which preset a finished 16:9 video uses.
    preset: str = "youtube_1080p60"
    # Friends on Discord in finished videos (only possible with a separate Discord track).
    include_voice_chat: bool = True
    # The music playing on stream (Spotify) in finished videos, kept under the
    # talking (render/music.py). The creator plays DMCA-free music and wants
    # it in every video (2026-10-10); each video can switch it off in Review.
    include_stream_music: bool = True

    @model_validator(mode="after")
    def _known_preset(self) -> "Render":
        if self.preset not in self.presets:
            raise ValueError(f"render.preset '{self.preset}' isn't one of the presets listed: "
                             f"{', '.join(self.presets)}")
        return self


class Storage(BaseModel):
    low_space_warning_gb: float = Field(100.0, ge=0)


class Twitch(BaseModel):
    vod_keep_days: int = Field(14, ge=1, le=365)
    download_quality: str = "1080p60"
    # Chat bots post automatically, so they never count as viewers reacting.
    ignore_chatters: list[str] = Field(default_factory=lambda: [
        "StreamElements", "Nightbot", "Moobot", "Streamlabs", "Fossabot",
        "Sery_Bot", "WizeBot", "SoundAlerts"])


class Llm(BaseModel):
    """The local AI (Ollama). Everything works without it; it adds judgement."""

    enabled: bool = True
    # One model reads text and looks at pictures (chosen 2026-10-04).
    model: str | None = "gemma4:12b"
    host: str = "http://127.0.0.1:11434"
    keep_alive: int = 0
    # Low: the same clip should get the same rating each time.
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    # How much of a clip's score is the AI's rating; the rest is what was heard
    # and seen. 0: shown, but it doesn't change which clips are picked. On the
    # creator's League stream the AI ranked their 👍 above their 👎 51% of the
    # time against the signals' 81%, so it waits until it agrees with them
    # (Settings shows how often it does, per game). 👍/👎 always decide.
    rating_weight: float = Field(0.0, ge=0.0, le=1.0)
    # Frames from the preview copy the AI looks at for each clip.
    frames_per_clip: int = Field(3, ge=0, le=8)

    @field_validator("host")
    @classmethod
    def _local_only(cls, v: str) -> str:
        # Everything stays on this PC (spec decision 1).
        from urllib.parse import urlparse

        if urlparse(v).hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(f"llm.host must be on this PC (127.0.0.1), got {v!r}")
        return v


class Publish(BaseModel):
    """Upload text and thumbnails for each video (publish.py)."""

    # Let's Play titles keep the series name; the AI writes {subtitle}.
    lets_play_title: str = "{game} - EP {episode} Part {part}: {subtitle}"
    # Added under every description, e.g. "Live on Twitch: twitch.tv/yourname".
    description_footer: str = ""
    thumbnails: int = Field(6, ge=1, le=12)
    # A Let's Play part gets a chapter about this often.
    chapter_every_min: float = Field(5.0, ge=1.0, le=30.0)

    @field_validator("lets_play_title")
    @classmethod
    def _title_fields(cls, v: str) -> str:
        try:
            v.format(game="g", episode=1, part=1, subtitle="s")
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError("lets_play_title can use {game}, {episode}, {part} and {subtitle} "
                             f"only: {exc}") from exc
        if "{subtitle}" not in v:
            raise ValueError("lets_play_title needs {subtitle}: it's where the AI's idea goes")
        return v


class Logging(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "WARNING"


class Settings(BaseModel):
    folders: Folders
    tools: Tools = Tools()
    performance: Performance = Performance()
    queue: Queue = Queue()
    companion: Companion = Companion()
    obs: Obs = Obs()
    analysis: Analysis = Analysis()
    scoring: Scoring = Scoring()
    clips: Clips = Clips()
    lets_play: LetsPlay = LetsPlay()
    highlights: Highlights = Highlights()
    shorts: Shorts = Shorts()
    render: Render = Render()
    effects: Effects = Effects()
    captions: Captions = Captions()
    storage: Storage = Storage()
    twitch: Twitch = Twitch()
    llm: Llm = Llm()
    publish: Publish = Publish()
    logging: Logging = Logging()

    # Where this instance was loaded from; not part of the YAML.
    source_path: Path | None = Field(default=None, exclude=True)

    @property
    def db_path(self) -> Path:
        """The clip library lives beside the cache so a backup can grab it alone."""
        return self.folders.cache / "ai-editor.db"

    @property
    def log_dir(self) -> Path:
        return self.folders.cache / "logs"

    def check_consistency(self) -> None:
        self.lets_play.check_consistency()
        self.shorts.check_consistency()
        if self.shorts.preset not in self.render.presets:
            raise ValueError(f"shorts.preset '{self.shorts.preset}' isn't one of the render "
                             f"presets: {', '.join(self.render.presets)}")
        self.clips.check_consistency()


def load_settings(path: str | os.PathLike[str] | None = None) -> Settings:
    """Read and validate settings.yaml.

    Raises SettingsInvalid with a readable explanation rather than a pydantic
    traceback, because this message is shown to the creator.
    """
    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not settings_path.exists():
        raise SettingsInvalid(f"No settings file at {settings_path}")

    raw = _read_yaml(settings_path)
    # Private values such as the OBS password live in a file beside
    # settings.yaml that git ignores, so they can never reach GitHub.
    local_path = local_settings_path(settings_path)
    if local_path.exists():
        raw = _merge(raw, _read_yaml(local_path))

    try:
        settings = Settings(**raw)
        settings.check_consistency()
    except ValidationError as exc:
        raise SettingsInvalid(_explain(exc)) from exc
    except ValueError as exc:
        raise SettingsInvalid(str(exc)) from exc

    settings.source_path = settings_path
    return settings


def local_settings_path(settings_path: Path) -> Path:
    """settings.yaml -> settings.local.yaml, in the same folder."""
    return settings_path.with_name(f"{settings_path.stem}.local{settings_path.suffix}")


def save_local_setting(settings_path: Path, section: str, key: str, value: Any) -> Path:
    """Write one value into the private local settings file, keeping the rest."""
    local_path = local_settings_path(settings_path)
    raw = _read_yaml(local_path) if local_path.exists() else {}
    raw.setdefault(section, {})[key] = value
    local_path.write_text(
        "# Private settings for this PC only. Never committed to git (see .gitignore).\n"
        + yaml.safe_dump(raw, sort_keys=False),
        encoding="utf-8",
    )
    return local_path


def save_local_settings(settings_path: Path, changes: dict[tuple[str, str], Any]) -> Settings:
    """Save several values to the private local file, all or none.

    ``changes`` maps (section, key) to the new value. The result is checked
    exactly as at start-up before anything is written, so a bad value can't
    leave AI-Editor unable to open. Everything else in the local file (the
    OBS password) is kept. Returns the settings as they now are.
    """
    local_path = local_settings_path(settings_path)
    local = _read_yaml(local_path) if local_path.exists() else {}
    for (section, key), value in changes.items():
        local.setdefault(section, {})[key] = value
    raw = _merge(_read_yaml(settings_path), local)
    try:
        settings = Settings(**raw)
        settings.check_consistency()
    except ValidationError as exc:
        raise SettingsInvalid(_explain(exc)) from exc
    except ValueError as exc:
        raise SettingsInvalid(str(exc)) from exc
    local_path.write_text(
        "# Private settings for this PC only. Never committed to git (see .gitignore).\n"
        + yaml.safe_dump(local, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    settings.source_path = settings_path
    return settings


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SettingsInvalid(f"{path.name} could not be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsInvalid(f"{path.name} must contain a list of settings")
    return raw


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Section by section: the local file only replaces the values it names."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _explain(exc: ValidationError) -> str:
    """Turn pydantic's error list into one sentence per problem."""
    lines = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"]) or "(top level)"
        lines.append(f"{where}: {err['msg']}")
    return "; ".join(lines)
