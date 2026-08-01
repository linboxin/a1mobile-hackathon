"""Transcript capture — who said what, on which call.

Pipecat 1.6 has no transcript processor, so this is a passive observer that
sits in the pipeline and records two frame types as they pass through:

    TranscriptionFrame  -> what the caller said   (place after the STT service)
    TTSTextFrame        -> what the judge said    (place after the TTS service)

It never modifies or swallows frames. Lines land in the Game so the host
console can show a live transcript; the public board only ever gets the
non-secret parts (see Game.public_state).
"""

from __future__ import annotations

from collections.abc import Callable

from pipecat.frames.frames import Frame, TranscriptionFrame, TTSTextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class TranscriptLogger(FrameProcessor):
    """Records caller and judge speech into the game without altering the flow."""

    def __init__(self, record: Callable[[str, str], None], **kwargs):
        super().__init__(**kwargs)
        self._record = record

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        try:
            if isinstance(frame, TranscriptionFrame) and frame.text.strip():
                self._record("player", frame.text.strip())
            elif isinstance(frame, TTSTextFrame) and frame.text.strip():
                self._record("judge", frame.text.strip())
        except Exception:  # a transcript must never break a live call
            pass
        await self.push_frame(frame, direction)
