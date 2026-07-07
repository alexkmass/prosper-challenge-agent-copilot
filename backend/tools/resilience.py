#
# Call resilience — catches non-fatal STT/LLM/TTS failures (ElevenLabs STT/TTS
# and the base LLM service all push ErrorFrame downstream on a failed
# request) and turns them into a spoken recovery line instead of letting the
# error dead-end the turn. A fatal ErrorFrame is passed through unchanged —
# that class of error is unrecoverable by design in Pipecat.
#

from pipecat.frames.frames import ErrorFrame, Frame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

DEFAULT_RECOVERY_MESSAGE = "Sorry, I had trouble with that — could you say that again?"


class CallResilienceProcessor(FrameProcessor):
    """Swallows non-fatal ErrorFrames and speaks a generic recovery line instead."""

    def __init__(self, recovery_message: str = DEFAULT_RECOVERY_MESSAGE) -> None:
        super().__init__()
        self._recovery_message = recovery_message

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, ErrorFrame) and not frame.fatal:
            await self.push_frame(TTSSpeakFrame(text=self._recovery_message), direction)
            return

        await self.push_frame(frame, direction)
