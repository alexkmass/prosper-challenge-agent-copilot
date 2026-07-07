from pipecat.frames.frames import ErrorFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection

from tools.resilience import CallResilienceProcessor


async def test_non_fatal_upstream_error_emits_recovery_line_same_direction():
    processor = CallResilienceProcessor(recovery_message="retry please")
    pushed: list[tuple[object, FrameDirection]] = []

    async def fake_push_frame(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append((frame, direction))

    processor.push_frame = fake_push_frame  # type: ignore[method-assign]

    await processor.process_frame(
        ErrorFrame(error="boom", fatal=False), FrameDirection.UPSTREAM
    )

    assert len(pushed) == 1
    frame, direction = pushed[0]
    assert isinstance(frame, TTSSpeakFrame)
    assert frame.text == "retry please"
    assert direction == FrameDirection.UPSTREAM


async def test_fatal_error_passthrough_keeps_original_error_frame():
    processor = CallResilienceProcessor()
    pushed: list[tuple[object, FrameDirection]] = []

    async def fake_push_frame(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append((frame, direction))

    processor.push_frame = fake_push_frame  # type: ignore[method-assign]
    fatal_error = ErrorFrame(error="fatal", fatal=True)

    await processor.process_frame(fatal_error, FrameDirection.UPSTREAM)

    assert pushed == [(fatal_error, FrameDirection.UPSTREAM)]


async def test_non_error_frame_passthrough():
    processor = CallResilienceProcessor()
    pushed: list[tuple[object, FrameDirection]] = []

    async def fake_push_frame(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append((frame, direction))

    processor.push_frame = fake_push_frame  # type: ignore[method-assign]
    normal_frame = TTSSpeakFrame(text="plain downstream frame")

    await processor.process_frame(normal_frame, FrameDirection.DOWNSTREAM)

    assert pushed == [(normal_frame, FrameDirection.DOWNSTREAM)]
