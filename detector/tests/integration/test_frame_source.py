"""`adapters.OpenCvFrameSource` against real video files and a real `cv2.VideoCapture`.

The frame source is the only thing that decides *what time a frame happened*, and every
duration in this system -- the FALL cooldown, the PPE windows, the durations the engine
sums into `/event/periodic-events` -- is a difference of two of its stamps. The pipeline
reads its own clock exactly once, at shutdown, so nothing downstream can correct a
timestamp this module gets wrong.

That makes two of these tests the load-bearing ones: a file is stamped from the media
clock, from zero, monotonically; a camera is stamped from the injected clock. Both are
observable only against a real capture, because the property under test is the semantics
of `CAP_PROP_POS_MSEC` -- specifically that reading it *after* `read()` gives the frame
just returned, while `CAP_PROP_POS_FRAMES` at that same moment already names the next one.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from worksite_detector.adapters import AdapterUnavailableError, OpenCvFrameSource

from tests.integration.conftest import CLIP_FPS

pytestmark = pytest.mark.requires_ultralytics

#: An epoch-shaped constant, far from any media position, so a stamp that came from the
#: clock can never be mistaken for one that came from the file.
EPOCH_MS = 1_700_000_000_000


class RecordingClock:
    """A clock that counts how often it was asked, and never returns a media-like number."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        return EPOCH_MS + self.calls


def _frames(path: Path, clock: RecordingClock | None = None) -> tuple[list, RecordingClock]:
    clock = clock or RecordingClock()
    source = OpenCvFrameSource(str(path), clock=clock)
    try:
        return list(source), clock
    finally:
        source.close()


def test_reads_every_frame_of_a_real_video_in_order(counting_clip: tuple) -> None:
    path, fills = counting_clip

    frames, _ = _frames(path)

    assert len(frames) == len(fills)
    assert [frame.index for frame in frames] == list(range(len(fills)))
    # The codec is lossy, so frames are placed by brightness rather than by exact value;
    # the clip was written with a strictly increasing fill for this reason.
    means = [float(frame.image.mean()) for frame in frames]
    assert means == sorted(means), f"frames arrived out of order: {means}"


def test_frames_carry_a_real_decoded_image(counting_clip: tuple) -> None:
    path, _ = counting_clip

    frames, _ = _frames(path)

    first = frames[0].image
    assert isinstance(first, np.ndarray)
    assert first.dtype == np.uint8
    assert first.shape == (64, 96, 3), "height, width, BGR -- what the clip was written as"


def test_a_video_file_is_stamped_from_its_own_media_clock(counting_clip: tuple) -> None:
    path, fills = counting_clip

    frames, _ = _frames(path)
    stamps = [frame.timestamp_ms for frame in frames]

    assert len(stamps) == len(fills)
    assert stamps[0] == 0, (
        "the first frame of a clip is at media position zero. A non-zero first stamp means "
        "the clock was read, or that CAP_PROP_POS_MSEC was read before read() rather than "
        "after -- which returns the *previous* frame's position."
    )
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps), (
        f"media positions must increase strictly, got {stamps}"
    )
    expected_step = 1000.0 / CLIP_FPS
    steps = [later - earlier for earlier, later in zip(stamps, stamps[1:], strict=False)]
    assert all(abs(step - expected_step) <= 2 for step in steps), (
        f"a {CLIP_FPS} fps clip advances {expected_step} ms per frame, got steps {steps}"
    )


def test_a_video_file_never_consults_the_clock(counting_clip: tuple) -> None:
    # Reproducibility is the whole point of the media clock: replaying the same file twice
    # must produce byte-identical event times, which one wall-clock reading would end.
    path, _ = counting_clip

    _, clock = _frames(path)

    assert clock.calls == 0


def test_replaying_the_same_file_produces_identical_timestamps(counting_clip: tuple) -> None:
    path, _ = counting_clip

    first, _ = _frames(path)
    second, _ = _frames(path)

    assert [frame.timestamp_ms for frame in first] == [frame.timestamp_ms for frame in second]


def test_a_numeric_source_is_read_as_a_camera_index(tmp_path: Path) -> None:
    # `isnumeric()` is the original's branch (line 236) and the rule every existing
    # configuration was written against: "0" is a webcam, not a file called `0`.
    with pytest.raises(AdapterUnavailableError) as excinfo:
        OpenCvFrameSource("99", clock=RecordingClock())

    assert "camera index 99" in str(excinfo.value)


def test_a_missing_file_is_fatal_at_construction(tmp_path: Path) -> None:
    # The original asked `while cap.isOpened()` and exited quietly with status 0, having
    # watched nothing at all, when the answer was no.
    missing = tmp_path / "no-such-clip.mp4"

    with pytest.raises(AdapterUnavailableError) as excinfo:
        OpenCvFrameSource(str(missing), clock=RecordingClock())

    assert str(missing) in str(excinfo.value), (
        "the path has to appear verbatim -- and unescaped, since operators read Windows "
        "paths out of these messages"
    )
    assert str(excinfo.value).startswith("cannot open video source"), (
        "a path must not be reported as a device"
    )


def test_an_unreadable_file_is_fatal_at_construction(tmp_path: Path) -> None:
    not_a_video = tmp_path / "notes.mp4"
    not_a_video.write_text("this is not a video", encoding="utf-8")

    with pytest.raises(AdapterUnavailableError):
        OpenCvFrameSource(str(not_a_video), clock=RecordingClock())


def test_close_is_idempotent(counting_clip: tuple) -> None:
    # The pipeline closes from a `finally` that may run alongside a signal handler.
    path, _ = counting_clip
    source = OpenCvFrameSource(str(path), clock=RecordingClock())

    source.close()
    source.close()


def test_iteration_after_close_yields_nothing_rather_than_raising(counting_clip: tuple) -> None:
    path, _ = counting_clip
    source = OpenCvFrameSource(str(path), clock=RecordingClock())
    source.close()

    assert list(source) == []


def test_the_source_is_exhausted_at_the_end_of_the_clip(counting_clip: tuple) -> None:
    path, fills = counting_clip
    source = OpenCvFrameSource(str(path), clock=RecordingClock())
    try:
        frames = iter(source)
        for _ in range(len(fills)):
            next(frames)

        with pytest.raises(StopIteration):
            next(frames)
    finally:
        source.close()
