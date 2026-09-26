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
from pydantic import BaseModel, Field, ValidationError, field_validator

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
        return {name: getattr(self, name) for name in self.model_fields}


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
    mark_moment_hotkey: str = "numpad+"
    mark_short_hotkey: str = "numpad-"
    confirmation_sound: bool = True
    sound_volume: float = Field(0.9, ge=0.05, le=1.0)
    start_with_windows: bool = False


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
    mode: Literal["split", "condense"] = "split"
    target_min: float = Field(30.0, gt=0)
    normal_range_min: tuple[float, float] = (25.0, 35.0)
    story_extension_preferred_max_min: float = 45.0
    story_extension_hard_max_min: float = 60.0
    trim_level: Literal["light", "standard", "tight"] = "light"
    penalties: SplitPenalties = SplitPenalties()
    bonus_hook_ending: float = -5.0
    leftover: Leftover = Leftover()
    recap_at_start: bool = False
    recap_max_sec: float = 15.0
    hook_endings: bool = True
    speedup_indicator: bool = True
    tolerance_pct: float = Field(15.0, ge=0, le=50)

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
    min_clip_score: float = Field(0.6, ge=0.0, le=1.0)
    ordering: Literal["chronological", "balanced", "best_last"] = "balanced"
    hook: bool = True
    hook_seconds: tuple[float, float] = (5.0, 15.0)
    allow_reused_clips: bool = False
    always_include_pinned: bool = True
    always_include_markers: bool = True


class SafeZone(BaseModel):
    bottom: float = Field(0.0, ge=0.0, le=0.6)
    right: float = Field(0.0, ge=0.0, le=0.6)
    top: float = Field(0.0, ge=0.0, le=0.6)


class Shorts(BaseModel):
    min_length_sec: float = Field(15.0, gt=0)
    max_length_sec: float = Field(60.0, gt=0)
    platform: Literal["youtube_shorts", "tiktok", "universal"] = "universal"
    layout: str = "facecam_top"
    follow_action: bool = False
    hook: bool = True
    must_make_sense_alone: bool = True
    link_to_full_video: bool = True
    spoiler_check_games: list[str] = Field(default_factory=list)
    safe_zones: dict[str, SafeZone] = Field(default_factory=dict)

    def check_consistency(self) -> None:
        if self.min_length_sec >= self.max_length_sec:
            raise ValueError("shorts.min_length_sec must be below max_length_sec")


class RenderPreset(BaseModel):
    width: int
    height: int
    fps: int
    bitrate: str


class Render(BaseModel):
    encoder: Literal["h264_nvenc", "hevc_nvenc"] = "h264_nvenc"
    nvenc_preset: str = "p5"
    loudness_target_lufs: float = -14.0
    presets: dict[str, RenderPreset] = Field(default_factory=dict)


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
    enabled: bool = False
    model: str | None = None
    keep_alive: int = 0


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
    storage: Storage = Storage()
    twitch: Twitch = Twitch()
    llm: Llm = Llm()
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
