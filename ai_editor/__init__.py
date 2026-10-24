"""AI-Editor: a local assistant editor for stream and Let's Play recordings.

Built to the two documents in Docs/:
  * Stream Auto-Editor - Project Specification v2.0
  * StreamCut User Manual (draft v1.0)

Everything runs locally and free, and the tool never interacts with a game
process in any way (specification section 6).
"""

import os as _os

# Nothing about you leaves this PC (the creator, 24 Oct): the Hugging Face
# download library Whisper's first download goes through, and Gradio, both stay
# quiet. Set before either is imported.
_os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
_os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
_os.environ.setdefault("DO_NOT_TRACK", "1")

__version__ = "0.29.0"
__product_name__ = "AI-Editor"
