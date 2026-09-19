"""The hallucination filter.

The two main cases are real segments from the creator's EP 1: a cutscene line
that must be kept, and "We'll see you next time." that Whisper invented over
game music.
"""

from __future__ import annotations

from ai_editor.analysis.transcript import (
    accepted_words,
    is_likely_hallucination,
    tidy_word,
    voice_detector_on,
)

REAL_DIALOGUE = {
    "s": 7.06, "e": 13.04, "text": "The beast? He helped us. I guess he did.",
    "avg_logprob": -0.148, "no_speech_prob": 0.0, "compression_ratio": 1.359,
    "words": [
        {"w": "The", "s": 7.06, "e": 7.50, "p": 0.20},
        {"w": "beast?", "s": 7.50, "e": 7.82, "p": 0.30},
        {"w": "He", "s": 8.36, "e": 8.88, "p": 0.96},
        {"w": "helped", "s": 8.88, "e": 9.12, "p": 0.99},
        {"w": "us.", "s": 9.12, "e": 9.42, "p": 1.00},
        {"w": "I", "s": 9.64, "e": 10.12, "p": 0.95},
        {"w": "guess", "s": 10.12, "e": 10.36, "p": 1.00},
        {"w": "he", "s": 10.36, "e": 10.48, "p": 0.99},
        {"w": "did.", "s": 10.48, "e": 10.68, "p": 1.00},
    ],
}

MUSIC_HALLUCINATION = {
    "s": 110.4, "e": 118.48, "text": "We'll see you next time.",
    "avg_logprob": -0.851, "no_speech_prob": 0.0, "compression_ratio": 0.758,
    "words": [
        {"w": "We'll", "s": 110.40, "e": 111.80, "p": 0.26},
        {"w": "see", "s": 113.05, "e": 114.45, "p": 0.86},
        {"w": "you", "s": 117.84, "e": 117.96, "p": 0.55},
        {"w": "next", "s": 117.96, "e": 117.98, "p": 0.16},
        {"w": "time.", "s": 117.98, "e": 118.48, "p": 0.91},
    ],
}

CREATOR_SIGN_OFF = {
    # The creator really saying it, clearly, at a normal pace: must survive.
    "s": 7500.0, "e": 7501.4, "text": "See you next time.",
    "avg_logprob": -0.2, "no_speech_prob": 0.0, "compression_ratio": 0.8,
    "words": [
        {"w": "See", "s": 7500.0, "e": 7500.3, "p": 0.97},
        {"w": "you", "s": 7500.3, "e": 7500.5, "p": 0.99},
        {"w": "next", "s": 7500.5, "e": 7500.8, "p": 0.98},
        {"w": "time.", "s": 7500.8, "e": 7501.4, "p": 0.99},
    ],
}


def test_real_dialogue_is_kept_despite_two_unsure_words():
    assert not is_likely_hallucination(REAL_DIALOGUE)


def test_invented_sign_off_over_music_is_set_aside():
    assert is_likely_hallucination(MUSIC_HALLUCINATION)


def test_a_genuine_sign_off_is_never_removed():
    """No banned-phrase list: the words themselves are never the reason."""
    assert not is_likely_hallucination(CREATOR_SIGN_OFF)


def test_repetition_loop_is_set_aside():
    stuck = dict(CREATOR_SIGN_OFF, compression_ratio=3.1)
    assert is_likely_hallucination(stuck)


def test_near_zero_confidence_and_whisper_says_not_speech():
    """From EP 1 with large-v3: noise transcribed as a word."""
    segment = {
        "avg_logprob": -0.5, "no_speech_prob": 0.7, "compression_ratio": 1.0,
        "words": [{"w": "Enough", "s": 1.0, "e": 1.3, "p": 0.01}],
    }
    assert is_likely_hallucination(segment)


def test_real_reaction_over_music_is_kept():
    """From EP 1 with large-v3: Whisper called this "not speech" (0.81), but it
    was a real shout over game music, 52% confident at a normal pace."""
    segment = {
        "avg_logprob": -0.6, "no_speech_prob": 0.81, "compression_ratio": 0.8,
        "words": [{"w": "Look", "s": 6676.0, "e": 6676.3, "p": 0.50},
                  {"w": "out!", "s": 6676.3, "e": 6676.7, "p": 0.54}],
    }
    assert not is_likely_hallucination(segment)


def test_unsure_but_quick_and_otherwise_confident_is_kept():
    """Mumbled but real speech: low word scores alone aren't enough."""
    segment = {
        "avg_logprob": -0.6, "no_speech_prob": 0.0, "compression_ratio": 1.0,
        "words": [
            {"w": "gonna", "s": 1.0, "e": 1.2, "p": 0.5},
            {"w": "grab", "s": 1.2, "e": 1.4, "p": 0.5},
            {"w": "that", "s": 1.4, "e": 1.6, "p": 0.5},
        ],
    }
    assert not is_likely_hallucination(segment)


def test_lone_unsure_word_smeared_over_music_is_set_aside():
    segment = {"avg_logprob": -0.8, "no_speech_prob": 0.0, "compression_ratio": 0.5,
               "words": [{"w": "We'll", "s": 110.4, "e": 111.8, "p": 0.26}]}
    assert is_likely_hallucination(segment)


def test_lone_quick_reaction_is_kept_even_if_unsure():
    segment = {"avg_logprob": -0.7, "no_speech_prob": 0.0, "compression_ratio": 0.5,
               "words": [{"w": "What?", "s": 50.0, "e": 50.4, "p": 0.45}]}
    assert not is_likely_hallucination(segment)


def test_accepted_words_keeps_order_and_reports_what_was_dropped():
    kept, dropped = accepted_words({"segments": [REAL_DIALOGUE, MUSIC_HALLUCINATION]})
    assert [w["w"] for w in kept][:3] == ["The", "beast?", "He"]
    assert [s["text"] for s in dropped] == ["We'll see you next time."]


def test_voice_detector_auto_follows_the_track():
    """Measured on EP 1: on a mixed track the detector dropped real dialogue."""
    assert voice_detector_on("auto", "mic") is True
    assert voice_detector_on("auto", "mixed") is False
    assert voice_detector_on("on", "mixed") is True
    assert voice_detector_on("off", "mic") is False


def test_lower_case_i_is_capitalised_in_english():
    assert tidy_word("i", "en") == "I"
    assert tidy_word("i'll", "en") == "I'll"
    assert tidy_word("i,", "en") == "I,"
    assert tidy_word("it", "en") == "it"
    assert tidy_word("inkling", "en") == "inkling"
    assert tidy_word("i", "fr") == "i", "only English"
