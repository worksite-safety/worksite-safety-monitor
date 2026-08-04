"""The whole detector, wired from a real video file to a real preview file.

Every other test in this tier isolates one adapter. This one asks the question none of
them can: do the four adapters actually satisfy the protocols `pipeline.Pipeline` was
written against? Those protocols are structural -- nothing declares that
`UltralyticsPoseModel` is a `_PoseModel` -- so the only proof is running the real loop
over real frames with the real rules and the real weights.

It is deliberately the smallest such run that can fail for a real reason: three frames of
a two-person photograph, an in-memory publisher, and a temporary output file.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
import pytest
from worksite_detector.adapters import (
    AnnotatingSink,
    OpenCvFrameSource,
    UltralyticsObjectModel,
    UltralyticsPoseModel,
)
from worksite_detector.config import Config
from worksite_detector.events import DetectionEvent
from worksite_detector.pipeline import Frame, ObjectDetection, PoseDetection, Pipeline
from worksite_detector.pose_rules import GestureDetector
from worksite_detector.ppe_rules import FallThrottle, PpeViolationTracker
from worksite_detector.publisher import InMemoryEventPublisher

pytestmark = pytest.mark.requires_ultralytics

CAMERA_NAME = "gate-1"

#: Any real epoch stamp is above this; any media position in a three-frame clip is far
#: below it. The gap is what makes "which clock stamped this event" an assertion.
EPOCH_FLOOR_MS = 1_000_000_000_000


class CountingSink:
    """Delegates to the real sink and records that it was reached, and with what."""

    def __init__(self, inner: AnnotatingSink) -> None:
        self._inner = inner
        self.writes: list[tuple[int, int, int]] = []
        self.closed = 0

    def write(
        self, frame: Frame, pose: PoseDetection, objects: Sequence[ObjectDetection]
    ) -> None:
        self.writes.append((frame.index, len(pose.keypoints_xy), len(list(objects))))
        self._inner.write(frame, pose, objects)

    def close(self) -> None:
        self.closed += 1
        self._inner.close()


def _clock() -> int:
    raise AssertionError(
        "the pipeline read its clock during the run. Every event time comes from the "
        "frame it was observed on; the only legitimate reading is the shutdown flush."
    )


@pytest.fixture()
def run(crowd_clip: Path, pose_weights: Path, ppe_weights: Path, tmp_path: Path) -> dict:
    """One complete detector run over the clip, and everything it left behind."""
    config = Config()
    target = tmp_path / "output_image.jpg"
    publisher = InMemoryEventPublisher()
    sink = CountingSink(AnnotatingSink(target))
    source = OpenCvFrameSource(str(crowd_clip), clock=_clock)

    shutdown_readings: list[int] = []

    def shutdown_clock() -> int:
        # The one reading the loop cannot take from a frame, because the loop has ended.
        shutdown_readings.append(EPOCH_FLOOR_MS)
        return EPOCH_FLOOR_MS

    Pipeline(
        frame_source=source,
        pose_model=UltralyticsPoseModel.load(
            pose_weights, confidence=config.thresholds.pose_confidence
        ),
        object_model=UltralyticsObjectModel.load(
            ppe_weights, confidence=config.thresholds.ppe_confidence
        ),
        sink=sink,
        publisher=publisher,
        gesture_detector=GestureDetector(
            config.gestures,
            CAMERA_NAME,
            keypoint_visibility=config.thresholds.keypoint_visibility,
            upright_left_idx=config.upright.left_idx,
            upright_right_idx=config.upright.right_idx,
            upright_angle=config.upright.angle_degrees,
        ),
        ppe_tracker=PpeViolationTracker(CAMERA_NAME, grace_ms=config.thresholds.ppe_grace_ms),
        fall_throttle=FallThrottle(config.thresholds.fall_cooldown_ms),
        clock=shutdown_clock,
        should_stop=lambda: False,
        camera_name=CAMERA_NAME,
    ).run()

    return {
        "events": publisher.events,
        "publisher": publisher,
        "sink": sink,
        "target": target,
        "shutdown_readings": shutdown_readings,
    }


def test_every_frame_reaches_the_sink(run: dict) -> None:
    # No early exit: the frame loop runs every stage on every frame, including the ones
    # the models found nothing in. The original skipped both on a person-free frame.
    writes = run["sink"].writes
    assert [index for index, _, _ in writes] == [0, 1, 2]
    assert all(people > 0 for _, people, _ in writes), "the clip holds people in every frame"


def test_the_preview_is_a_complete_image_when_the_run_ends(run: dict) -> None:
    target: Path = run["target"]

    decoded = cv2.imdecode(np.frombuffer(target.read_bytes(), np.uint8), cv2.IMREAD_COLOR)

    assert decoded is not None
    assert max(decoded.shape[:2]) == 640, "the preview is scaled for the polling browser"
    assert [path.name for path in target.parent.iterdir()] == [target.name], (
        "no temporary file survives a clean shutdown"
    )


def test_everything_is_closed_exactly_once(run: dict) -> None:
    assert run["sink"].closed == 1
    assert run["publisher"].closed is True


def test_the_clock_is_read_only_at_shutdown(run: dict) -> None:
    # `_clock` on the frame source raises if it is called at all, so reaching here proves
    # no frame was stamped from a wall clock; the flush is the one legitimate reading.
    assert run["shutdown_readings"] == [EPOCH_FLOOR_MS]


def test_published_events_are_stamped_from_the_media_clock(run: dict) -> None:
    events: list[DetectionEvent] = run["events"]

    for event in events:
        assert isinstance(event, DetectionEvent)
        assert event.camera_name == CAMERA_NAME
        assert 0.0 <= event.confidence <= 1.0
        assert event.start_time_ms < EPOCH_FLOOR_MS, (
            f"{event.event_type.value} was stamped {event.start_time_ms}, which is a wall "
            "clock reading. Every event's time comes from the frame it was observed on, "
            "and a replay of the same file must produce the same times."
        )


def test_the_run_publishes_the_violations_the_footage_holds(run: dict) -> None:
    # bus.jpg is a street scene: nobody in it is wearing a helmet or a high-vis jacket,
    # and `best.pt` says so at the configured 0.6 gate. The windows those detections open
    # are still open when the clip ends, so the shutdown flush is what publishes them --
    # the flush the original never had, which is how it lost NO_JACKET entirely.
    events: list[DetectionEvent] = run["events"]

    assert events, "three frames of unprotected workers should not be a silent run"
    assert all(event.time_period_ms is not None for event in events), (
        "these are periodic events and the engine sums their durations"
    )
