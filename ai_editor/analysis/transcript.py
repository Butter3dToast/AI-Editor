"""Speech to text, with a timestamp for every word (spec section 7.3).

Word timestamps are what later stages need most: captions that appear as each
word is said, and cuts that never land mid-word.

Transcription runs one piece at a time, never batched. Measured on the
creator's EP 1: the batched pipeline decodes each chunk of up to 30 seconds in
a single pass, and when Whisper lost its way partway through a chunk (a voice
under game music) the rest of that chunk was silently dropped -- 0 to 4 words
where there were over 70. Sequential decoding resumes from where each phrase
ends, so nothing is skipped, and it still ran at over 80x real time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..config import Settings
from ..errors import OutOfGraphicsMemory
from ..logging_setup import get_logger
from ..models import is_out_of_memory, whisper_model

log = get_logger(__name__)


def voice_detector_on(setting: str, voice_role: str) -> bool:
    """Whether to let the voice detector skip audio before transcribing.

    On a clean microphone track the detector is reliable, and skipping the
    silences stops Whisper inventing words over them. On a mixed track it
    measured badly: with it on, EP 1 kept 218 words in two test stretches;
    with it off, 295 -- the difference almost all real dialogue under music.
    So "auto" uses it only where it helps.
    """
    if setting == "on":
        return True
    if setting == "off":
        return False
    return voice_role == "mic"


# More sensitive than the detector's default (0.5), which missed quieter speech.
VOICE_DETECTOR_PARAMETERS = {"threshold": 0.35, "speech_pad_ms": 400}


def transcribe(
    settings: Settings,
    wav_16k: Path,
    duration_sec: float,
    on_progress: Callable[[float], None] | None = None,
    *,
    use_voice_detector: bool = True,
) -> dict[str, Any]:
    """Transcribe a 16 kHz mono WAV. Returns plain data, ready to save as JSON."""
    language = None if settings.analysis.language == "auto" else settings.analysis.language
    segments_out: list[dict[str, Any]] = []
    word_count = 0

    with whisper_model(settings) as model:
        try:
            segments, info = model.transcribe(  # type: ignore[attr-defined]
                str(wav_16k),
                language=language,
                word_timestamps=True,
                beam_size=5,
                vad_filter=use_voice_detector,
                vad_parameters=VOICE_DETECTOR_PARAMETERS if use_voice_detector else None,
                # Each phrase is decoded on its own merits. Carrying the
                # previous text forward lets one mistake snowball into a
                # repeated phrase for minutes on a two-hour recording.
                condition_on_previous_text=False,
            )
            # `segments` is lazy: the real work happens while iterating, which
            # is also what lets progress be reported as it goes.
            for segment in segments:
                words = [
                    {"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3),
                     "p": round(w.probability, 3)}
                    for w in segment.words or ()
                    if w.word.strip()
                ]
                word_count += len(words)
                # Whisper's own quality measures are kept so phrases can be
                # judged later (see is_likely_hallucination) without having
                # to transcribe again.
                segments_out.append({
                    "s": round(segment.start, 3),
                    "e": round(segment.end, 3),
                    "text": segment.text.strip(),
                    "avg_logprob": _maybe_round(getattr(segment, "avg_logprob", None)),
                    "no_speech_prob": _maybe_round(getattr(segment, "no_speech_prob", None)),
                    "compression_ratio": _maybe_round(getattr(segment, "compression_ratio", None)),
                    "words": words,
                })
                if on_progress and duration_sec:
                    on_progress(min(1.0, segment.end / duration_sec))
        except Exception as exc:  # noqa: BLE001
            if is_out_of_memory(exc):
                raise OutOfGraphicsMemory() from exc
            raise

    if on_progress:
        on_progress(1.0)
    log.info("Transcribed %d words in %d segments (language %s)",
             word_count, len(segments_out), info.language)
    return {
        "model": settings.analysis.transcription_model,
        "voice_detector": use_voice_detector,
        "language": info.language,
        "language_probability": round(float(info.language_probability), 3),
        "segments": segments_out,
    }


def _maybe_round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 3)


# --- Hallucination filter ---------------------------------------------------
#
# Fed music or game noise, Whisper sometimes "hears" phrases that were never
# said -- very often YouTube sign-offs like "see you next time" or "thanks for
# watching", because that is what its training audio sounded like at the end.
#
# On the creator's own footage, one such phrase over game music had words 16-91%
# certain, spoken one word every 1.6 seconds; the real dialogue around it was
# ~93% certain at ~2.5 words a second. So a phrase is set aside only when it is
# BOTH unsure AND implausibly slow (or Whisper itself thinks it isn't speech).
#
# Deliberately no list of banned phrases: the creator may really say "see you
# next time" at the end of an episode, and that must survive.

MIN_MEAN_WORD_PROBABILITY = 0.6
MIN_WORDS_PER_SECOND = 1.0
# Whisper often reports no_speech_prob as 0.0 on game audio, so the average
# log-probability is the backup "unsure overall" check. Both limits are
# Whisper's own defaults (logprob_threshold, compression_ratio_threshold), not
# values tuned to one example.
MAX_NO_SPEECH_PROBABILITY = 0.5
# "Probably not speech" alone isn't enough: with large-v3 on EP 1, Whisper said
# that about real reactions shouted over game music ("Look out!", "Oh, shit!",
# 38-60% confident) as well as about noise ("Oh", "Enough", "Go", 1-23%). Only
# the second group is set aside.
NO_SPEECH_MAX_CONFIDENCE = 0.35
MIN_AVG_LOGPROB = -1.0
MAX_COMPRESSION_RATIO = 2.4  # "stuck repeating itself"


def is_likely_hallucination(segment: dict[str, Any]) -> bool:
    """True when a transcribed phrase is probably not something anyone said."""
    words = segment.get("words") or []
    if not words:
        return True
    ratio = segment.get("compression_ratio")
    if ratio is not None and ratio > MAX_COMPRESSION_RATIO:
        return True

    mean_probability = sum(w["p"] for w in words) / len(words)
    if mean_probability >= MIN_MEAN_WORD_PROBABILITY:
        return False

    # Holds for a lone word too: a real one-word reaction ("What?") is over in
    # well under a second, while an invented one tends to be smeared across
    # the music it was heard in.
    span = max(words[-1]["e"] - words[0]["s"], 0.01)
    too_slow = len(words) / span < MIN_WORDS_PER_SECOND
    no_speech = (
        (segment.get("no_speech_prob") or 0.0) > MAX_NO_SPEECH_PROBABILITY
        and mean_probability < NO_SPEECH_MAX_CONFIDENCE
    )
    logprob = segment.get("avg_logprob")
    very_unsure = logprob is not None and logprob < MIN_AVG_LOGPROB
    return too_slow or no_speech or very_unsure


def tidy_word(text: str, language: str | None) -> str:
    """Small, safe clean-ups for display.

    large-v3 sometimes writes the English pronoun in lower case ("i think",
    "i'll"). Only the standalone word and its contractions are touched.
    """
    if language == "en":
        bare = text.strip(".,!?;:\"'")
        if bare == "i" or bare.startswith(("i'", "i’")):
            return text.replace("i", "I", 1)
    return text


def accepted_words(
    transcript: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a saved transcript into (words to keep, phrases set aside)."""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    language = transcript.get("language")
    for segment in transcript.get("segments", []):
        if is_likely_hallucination(segment):
            dropped.append(segment)
        else:
            kept.extend(
                {**w, "w": tidy_word(w["w"], language)} for w in segment.get("words") or []
            )
    return kept, dropped
