"""Hand-written test doubles for the four seams the pipeline talks through.

Hand-written rather than `unittest.mock` on purpose. A `Mock` answers any
attribute with another `Mock`, so a test that calls the wrong method, or the
right method with the wrong arguments, still passes -- and the pipeline's whole
reason for existing is that the original could not be tested at all without a
camera, a GPU and a broker. These fakes fail loudly instead: a scripted model
that runs out of frames raises, and a sink records what it was actually given.

Everything here is deliberately dumb. They are shared between the pose, PPE and
pipeline suites, so a behaviour added here to suit one test is a behaviour the
other two silently inherit.
"""
from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any


class FakeClock:
    """A clock that only moves when a test moves it.

    The original read `time.time()` and `datetime.now()` on every frame, which
    is why its 3-minute FALL cooldown and its PPE windows could not be tested
    without sleeping. Every duration in the replacement comes from here, so a
    3-second violation takes no wall-clock time to test.

    Milliseconds since the epoch, matching `DetectionEvent.start_time_ms` and
    the engine's `Long startTime`.
    """

    def __init__(self, start_ms: int = 0) -> None:
        self._now_ms = start_ms

    def now(self) -> int:
        """The current time in milliseconds. Unchanged until `advance`."""
        return self._now_ms

    def advance(self, ms: int) -> None:
        """Move forward by `ms` milliseconds.

        Raises:
            ValueError: If `ms` is negative. Time running backwards would make
                a duration negative and every threshold comparison meaningless,
                and it is never what a test meant.
        """
        if ms < 0:
            raise ValueError(f"a clock cannot run backwards; advance got {ms}")
        self._now_ms += ms


class FakeFrameSource:
    """A finite sequence of frames, standing in for `cv2.VideoCapture`.

    A frame is whatever the test decides -- an index, a label, a sentinel
    object. Nothing in the unit suite looks inside one; frames exist to be
    counted and to be handed to the scripted models in order.
    """

    def __init__(self, frames: Sequence[Any]) -> None:
        self.frames: tuple[Any, ...] = tuple(frames)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.frames)

    def __len__(self) -> int:
        return len(self.frames)


class _ScriptedModel:
    """Returns a prepared result per call, and records what it was called with."""

    def __init__(self, per_frame_returns: Sequence[Any]) -> None:
        self._returns: tuple[Any, ...] = tuple(per_frame_returns)
        self.calls: list[Any] = []

    def __call__(self, frame: Any) -> Any:
        """The result scripted for this call, in order.

        Raises:
            AssertionError: If called more times than the script has entries.
                Silently repeating the last result, or returning nothing, would
                let a pipeline that reads a frame twice look correct.
        """
        index = len(self.calls)
        if index >= len(self._returns):
            raise AssertionError(
                f"{type(self).__name__} was called {index + 1} times but only "
                f"{len(self._returns)} results were scripted"
            )
        self.calls.append(frame)
        return self._returns[index]

    @property
    def call_count(self) -> int:
        return len(self.calls)


class ScriptedPoseModel(_ScriptedModel):
    """Stands in for the pose model. Each entry is that frame's people --
    normally a list of `PersonObservation`, empty for a frame with nobody in
    it (the case `aiModule.py` line 310 skips with a bare `continue`)."""


class ScriptedObjectModel(_ScriptedModel):
    """Stands in for the PPE model. Each entry is that frame's detections --
    normally a list of `ObjectDetection`, empty for a clean frame."""


class RecordingSink:
    """Captures everything written to it, in order.

    Stands in for the Kafka producer. `writes` is the assertion surface: what
    was published, in what order, with what fields.
    """

    def __init__(self) -> None:
        self.writes: list[Any] = []

    def write(self, item: Any) -> None:
        self.writes.append(item)

    def __len__(self) -> int:
        return len(self.writes)
