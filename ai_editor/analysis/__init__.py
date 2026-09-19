"""Analysis: finding out what happens in a recording (spec section 7.3).

Phase 1B covers the audio: transcript, loudness, silence, and sound events.
Later phases add chat velocity (1C), markers (1D), and in Phase 2 scene
changes, faces, and AI moment rating, each as its own module here.
"""

from .pipeline import AnalysisResult, analyze_recording, resolve_recording

__all__ = ["AnalysisResult", "analyze_recording", "resolve_recording"]
