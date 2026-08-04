"""Unit tests for `worksite_detector.pipeline` -- the per-frame flow itself.

This module replaces `aiModule.py` lines 280-535, and one line of it carries the two
most user-visible defects in the project. Line 310::

    if results[0].keypoints.shape[1] == 0:
        ...
        continue

skips the *entire* rest of the frame whenever the pose model found nobody. Everything
after it -- the PPE boxes, the FALL branch, the violation windows, the `imwrite` that
feeds the web app's "video stream" -- is inside the block that `continue` jumps over.

1. **Falls are silently discarded.** A person lying on the ground is precisely what a
   pose model is worst at detecting, so the skip is aimed at the one event the system
   exists to catch. On the baseline recording (`tests/data/baseline/PROVENANCE.md`) the
   falls are at 15733 ms and 24066 ms; the first frame had no person in it, so the
   original published only the second. The incident was reported **8.3 seconds late**
   and the first fall vanished with nothing logged.
2. **The video preview freezes.** The same `continue` skips the `imwrite` at line 525,
   so `output_image.jpg` stops updating on person-free frames. The engine serves that
   one file and the browser polls it every 100 ms, so the operator sees a still picture
   and cannot tell it from a working camera.

Both have one cure: a single linear flow per frame with no early exit. The first six
tests below are that contract, and they are the ones a faithful port of the original
cannot pass.

Decisions this file makes that the test list left open, so that the GREEN half has one
answer rather than three:

* **Publish order within one frame is FALL, then gestures, then PPE window closures.**
  `KafkaEventPublisher.publish` flushes after every send, so publish order is durability
  order: if the process dies or the broker drops mid-frame, what has already gone is
  what survives. A gesture losing an event costs a statistic; a FALL losing one is the
  system failing at the thing it exists for. Processing order -- people, then boxes --
  would put the gestures first, but that order is an artifact of how the loop reads a
  frame, whereas urgency is a requirement, and the requirement wins.
  `test_publish_order_is_deterministic` pins it so nobody later tidies the publish order
  back into processing order without seeing what it trades away.
* **`should_stop` is consulted once before each frame**, never after: a stop signal that
  costs one more frame is a stop signal that did not stop.
* **A frame whose stage raised is abandoned, and the loop survives it.** The remaining
  frames are processed normally and the failure costs one ERROR record. A single bad
  frame ending a safety detector's run is the failure shape line 310 already has, and a
  half-annotated frame written from a half-failed pipeline is worse than a visibly
  missing one: the operator cannot tell a stale preview from a fresh one, which is the
  confusion the frozen-preview defect already creates.
* **A failing frame *source* is fatal and propagates**, through a `finally` that closes
  everything. There are no more frames to read, so continuing would spin.
* **The clock is called, not queried: `clock()`.** The frozen signature says so; that
  `fakes.FakeClock` spells its reading `now()` is the fixture's business and not the
  seam's, so the tests below inject the bound `FakeClock.now`. Leaving both spellings
  open would let GREEN depend on either and turn an unpinned choice into a coupling.
* **The sink is called `write(frame, pose, objects)`** -- the whole `Frame`, not the bare
  image. The annotating sink draws the skeletons and the violation boxes, so it needs
  both detection results, and it is where a timestamp or an index would be stamped or
  logged; unwrapping the frame on its behalf would put that decision in this module.

Timestamps come from the frame, never from the clock: `test_rules_use_frame_timestamp_
not_the_clock` and `test_pipeline_imports_no_cv2_ultralytics_kafka_or_time` are two
halves of the same requirement. The original stamped every event `int(time.time()*1000)`
at the moment of publication rather than the moment of observation, which is why none
of its timing behaviour could be tested without sleeping.

**Deliberately left unpinned**, considered and left to the implementation rather than
overlooked:

* **Two `fall` boxes on one frame.** Every FALL test here carries exactly one, so the
  collapse rule -- max, first, or one throttle attempt per box -- is open. The throttle
  makes the published outcome identical for any of them on a single fall, and inventing
  a rule from no evidence would pin a number the baseline clip cannot arbitrate.
* **Whether `forget` is called, and with which ids.** `GestureDetector` state is keyed by
  an externally supplied person id, and this pipeline derives that id from the person's
  position in one frame's pose output, so no id survives a frame in any meaningful sense.
  What to forget therefore depends on a tracker this unit does not have; the doubles
  below tolerate `forget` being called or not, and no test asserts either way.
"""
from __future__ import annotations

import ast
import logging
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests._support.builders import (
    PersonObservation as FixtureObservation,
    frame_sequence,
    make_person,
)
from tests._support.fakes import (
    FakeClock,
    FakeFrameSource,
    RecordingSink,
    ScriptedObjectModel,
    ScriptedPoseModel,
)
from worksite_detector.events import DetectionEvent, EventType
from worksite_detector.pipeline import Frame, ObjectDetection, Pipeline, PoseDetection
from worksite_detector.ppe_rules import FallThrottle, PpeViolationTracker
from worksite_detector.publisher import InMemoryEventPublisher

# Published verbatim on every event; the dashboard groups violations by it.
CAMERA = "kamera-üst"

# The injected clock sits nowhere near any frame timestamp, so an event stamped from it
# is off by nine orders of magnitude rather than by a plausible few milliseconds.
CLOCK_MS = 999_000_000

# timedelta(minutes=3), aiModule.py line 437.
FALL_COOLDOWN_MS = 180_000

# The documented PPE default; see ppe_rules and PROVENANCE.md for how it was measured.
GRACE_MS = 1500

# `logging.getLogger(__name__)` inside the module, which is the name an operator raises
# or silences independently of the rest of the detector.
PIPELINE_LOGGER = "worksite_detector.pipeline"

PIPELINE_SOURCE = (
    Path(__file__).resolve().parent.parent / "src" / "worksite_detector" / "pipeline.py"
)

# `time` is in here with the other three on purpose: a stray `time.time()` is how the
# original's timestamps became untestable, and an AST scan is the only check that sees
# an import deferred into a function body.
FORBIDDEN_IMPORTS = {"cv2", "ultralytics", "kafka", "time"}

#: A frame on which the pose model found nobody -- 278 of the baseline clip's 986.
NOBODY = PoseDetection(keypoints_xy=[], keypoint_conf=[], box_conf=[])


# --------------------------------------------------------------------------
# Fixtures and helpers
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Image:
    """Stands in for the decoded frame.

    Opaque by contract: the pipeline may hand it to a model or to the sink and must
    never look inside it. It carries an index only so a test can say *which* frame
    reached the sink.
    """

    index: int


def _frames(n: int, *, start_ms: int = 0, step_ms: int = 100) -> list[Frame]:
    """`n` frames, `step_ms` apart. The default 100 ms is the rate the original ran at."""
    return [
        Frame(image=_Image(index), timestamp_ms=timestamp_ms, index=index)
        for index, timestamp_ms in enumerate(
            frame_sequence(n, start_ms=start_ms, step_ms=step_ms)
        )
    ]


def _frame_at(timestamp_ms: int, index: int = 0) -> Frame:
    """One frame with an exact timestamp, for the tests that assert on it."""
    return Frame(image=_Image(index), timestamp_ms=timestamp_ms, index=index)


def _pose_of(*people: FixtureObservation) -> PoseDetection:
    """One frame's pose output, built from `builders.make_person` stick figures."""
    return PoseDetection(
        keypoints_xy=[list(person.keypoints_xy) for person in people],
        keypoint_conf=[list(person.keypoint_conf) for person in people],
        box_conf=[person.detection_confidence for person in people],
    )


def _box(label: str, confidence: float) -> ObjectDetection:
    """One PPE-model box. `label` is the raw model class, not the engine's event name."""
    return ObjectDetection(label=label, confidence=confidence, box=(10, 20, 30, 40))


def _written_indices(sink: RecordingSink) -> list[int]:
    """The index of every frame handed to the sink, in order."""
    return [frame.index for frame, _pose, _objects in sink.writes]


def _writes(sink: RecordingSink) -> list[tuple[Frame, PoseDetection, list[ObjectDetection]]]:
    """Everything the sink was handed, with the detections normalised to a list.

    The pipeline may pass the object model's output through as it found it or as a
    tuple; that is not what any test here is about, and the contents are asserted
    exactly either way.
    """
    return [(frame, pose, list(objects)) for frame, pose, objects in sink.writes]


# --------------------------------------------------------------------------
# Local doubles
#
# `tests/_support/fakes.py` is frozen and covers the frame source, the two models, the
# sink and the clock. It has nothing for the three rule objects the pipeline drives, no
# `close()` on the source or the sink, and no way to make a model raise -- so the four
# lifecycle tests, the two throttle tests and every "was this collaborator called with
# these arguments" test need the doubles below. Each one is the smallest thing that
# records what it was asked to do; none of them decides anything.
# --------------------------------------------------------------------------


class ClosingFrameSource(FakeFrameSource):
    """`FakeFrameSource` plus the `close()` the pipeline owes it.

    The original released its capture only on the normal path, so anything raising out
    of the frame loop leaked the camera handle.
    """

    def __init__(self, frames: Sequence[Any]) -> None:
        super().__init__(frames)
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


class ExplodingFrameSource(ClosingFrameSource):
    """Yields its frames and then fails, the way a camera unplugged mid-run does."""

    def __init__(self, frames: Sequence[Any], error: BaseException) -> None:
        super().__init__(frames)
        self._error = error

    def __iter__(self) -> Iterator[Any]:
        yield from self.frames
        raise self._error


class ClosingSink(RecordingSink):
    """`RecordingSink` taking the three-argument sink call, plus `close()`.

    The frozen fake records a single `item`; the annotated-frame sink needs the frame
    *and* both detection results to draw, so each write is recorded as the triple it
    was called with.
    """

    def __init__(self) -> None:
        super().__init__()
        self.close_count = 0

    def write(  # type: ignore[override]
        self, frame: Frame, pose: PoseDetection, objects: Sequence[ObjectDetection]
    ) -> None:
        self.writes.append((frame, pose, objects))

    def close(self) -> None:
        self.close_count += 1


class ExplodingPoseModel(ScriptedPoseModel):
    """Scripted, except that an entry which is an exception is raised instead of returned."""

    def __call__(self, frame: Any) -> Any:
        result = super().__call__(frame)
        if isinstance(result, BaseException):
            raise result
        return result


class RecordingGestureDetector:
    """Records every `update`, and returns whatever the test scripted for that call.

    Structural stand-in for `pose_rules.GestureDetector`: the pipeline is what feeds it
    people, and this records exactly which people, in which order, with which
    confidence.
    """

    def __init__(self, per_call_returns: Sequence[Sequence[DetectionEvent]] = ()) -> None:
        self._returns = tuple(tuple(events) for events in per_call_returns)
        self.updates: list[tuple[int, Any]] = []
        self.forgotten: list[list[int]] = []

    def update(self, frame_time_ms: int, observation: Any) -> list[DetectionEvent]:
        index = len(self.updates)
        self.updates.append((frame_time_ms, observation))
        return list(self._returns[index]) if index < len(self._returns) else []

    def forget(self, person_ids: Any) -> None:
        self.forgotten.append(list(person_ids))

    @property
    def states(self) -> Mapping[int, Any]:
        return {}


class RecordingPpeTracker:
    """Records every `observe` and `flush`, and returns whatever the test scripted.

    Structural stand-in for `ppe_rules.PpeViolationTracker`. `observations` is the
    assertion surface for the label mapping and for the once-per-frame contract; the
    real tracker is used instead wherever a test is about windows rather than wiring.
    """

    def __init__(
        self,
        observe_returns: Sequence[Sequence[DetectionEvent]] = (),
        flush_returns: Sequence[DetectionEvent] = (),
    ) -> None:
        self._observe_returns = tuple(tuple(events) for events in observe_returns)
        self._flush_returns = tuple(flush_returns)
        self.observations: list[tuple[int, dict[EventType, float]]] = []
        self.flush_calls: list[int] = []

    def observe(
        self, frame_time_ms: int, violations: Mapping[EventType, float]
    ) -> list[DetectionEvent]:
        index = len(self.observations)
        self.observations.append((frame_time_ms, dict(violations)))
        return list(self._observe_returns[index]) if index < len(self._observe_returns) else []

    def flush(self, now_ms: int) -> list[DetectionEvent]:
        self.flush_calls.append(now_ms)
        return list(self._flush_returns) if len(self.flush_calls) == 1 else []


class StopAfter:
    """A stop signal that allows `frames` frames through.

    Consulted once before each frame, so the fourth consultation of `StopAfter(3)` is
    what ends the run -- a stop that takes effect only after one more frame has been
    processed is not a stop.
    """

    def __init__(self, frames: int) -> None:
        self._frames = frames
        self.calls = 0

    def __call__(self) -> bool:
        self.calls += 1
        return self.calls > self._frames


@dataclass(slots=True)
class Rig:
    """One wired pipeline and every collaborator it was built from."""

    pipeline: Pipeline
    source: ClosingFrameSource
    pose_model: ScriptedPoseModel
    object_model: ScriptedObjectModel
    sink: ClosingSink
    publisher: InMemoryEventPublisher
    gestures: Any
    ppe: Any
    throttle: Any
    clock: FakeClock
    should_stop: Any

    def run(self) -> None:
        self.pipeline.run()


def _rig(
    frames: Sequence[Frame],
    *,
    pose: Sequence[Any] | None = None,
    objects: Sequence[Any] | None = None,
    gesture_returns: Sequence[Sequence[DetectionEvent]] = (),
    observe_returns: Sequence[Sequence[DetectionEvent]] = (),
    flush_returns: Sequence[DetectionEvent] = (),
    gesture_detector: Any = None,
    ppe_tracker: Any = None,
    fall_throttle: Any = None,
    source: ClosingFrameSource | None = None,
    pose_model: ScriptedPoseModel | None = None,
    clock_ms: int = CLOCK_MS,
    should_stop: Any = None,
) -> Rig:
    """Wire a pipeline whose every seam is a double this test can read back.

    Defaults are the person-free, detection-free frame -- the case the original skips.
    """
    source = source if source is not None else ClosingFrameSource(frames)
    pose_model = (
        pose_model
        if pose_model is not None
        else ScriptedPoseModel(list(pose) if pose is not None else [NOBODY] * len(frames))
    )
    object_model = ScriptedObjectModel(
        [list(detections) for detections in objects]
        if objects is not None
        else [[] for _ in frames]
    )
    sink = ClosingSink()
    publisher = InMemoryEventPublisher()
    gestures = (
        gesture_detector
        if gesture_detector is not None
        else RecordingGestureDetector(gesture_returns)
    )
    ppe = (
        ppe_tracker
        if ppe_tracker is not None
        else RecordingPpeTracker(observe_returns, flush_returns)
    )
    throttle = fall_throttle if fall_throttle is not None else FallThrottle(FALL_COOLDOWN_MS)
    clock = FakeClock(clock_ms)
    stop = should_stop if should_stop is not None else (lambda: False)

    pipeline = Pipeline(
        frame_source=source,
        pose_model=pose_model,
        object_model=object_model,
        sink=sink,
        publisher=publisher,
        gesture_detector=gestures,
        ppe_tracker=ppe,
        fall_throttle=throttle,
        # The bound reading, so the pipeline's only way to use it is `clock()`.
        clock=clock.now,
        should_stop=stop,
        camera_name=CAMERA,
    )
    return Rig(
        pipeline=pipeline,
        source=source,
        pose_model=pose_model,
        object_model=object_model,
        sink=sink,
        publisher=publisher,
        gestures=gestures,
        ppe=ppe,
        throttle=throttle,
        clock=clock,
        should_stop=stop,
    )


# --------------------------------------------------------------------------
# The frame contract -- the fix for both headline defects
# --------------------------------------------------------------------------


def test_person_free_frame_still_writes_to_sink() -> None:
    # aiModule.py:310 `continue`s past the imwrite at line 525, so on a frame with
    # nobody in it output_image.jpg is not rewritten and the operator's preview freezes
    # on the last populated frame with nothing to distinguish it from a live one.
    frames = _frames(1)
    rig = _rig(frames)

    rig.run()

    assert _writes(rig.sink) == [(frames[0], NOBODY, [])]


def test_person_free_frame_still_calls_ppe_observe() -> None:
    # The same `continue` never tells the tracker the frame happened, so a violation
    # that ended because the worker walked out of shot stays open and is later published
    # with a duration covering their absence (bug #15).
    rig = _rig([_frame_at(1234)])

    rig.run()

    assert rig.ppe.observations == [(1234, {})]


def test_person_free_frame_with_a_violation_is_tracked() -> None:
    # Impossible in the original: the PPE boxes are read at line 411, inside the block
    # line 310 skips, so a no-helmet box on a person-free frame was never even looked at.
    rig = _rig([_frame_at(1234)], objects=[[_box("no-helmet", 0.75)]])

    rig.run()

    assert rig.ppe.observations == [(1234, {EventType.NO_HELMET: 0.75})]


def test_fall_on_a_person_free_frame_is_published() -> None:
    # THE headline defect. The FALL branch at line 434 is inside the block line 310
    # skips, and a person on the ground is the hardest case for a pose model. On the
    # baseline clip the falls are at 15733 ms and 24066 ms; the first frame had nobody
    # detected in it, so the original published only the second -- the incident was
    # reported 8.3 seconds late and the first fall vanished with nothing logged.
    rig = _rig([_frame_at(15_733)], objects=[[_box("fall", 0.86)]])

    rig.run()

    assert rig.publisher.events == [
        DetectionEvent(
            event_type=EventType.FALL,
            start_time_ms=15_733,
            confidence=0.86,
            camera_name=CAMERA,
            time_period_ms=None,
        )
    ]


def test_sink_written_exactly_once_per_frame() -> None:
    # One write per frame, whatever was or was not detected: the preview must never
    # stall (bug #9), and it must never be written twice for one frame either, which
    # would make a stalled camera look busy. Each write carries its own frame's
    # detections, so the overlay cannot show the last populated frame's skeletons over
    # a later one -- a subtler version of the same freeze.
    frames = _frames(5)
    pose = [
        NOBODY,
        _pose_of(make_person()),
        NOBODY,
        _pose_of(make_person(), make_person()),
        NOBODY,
    ]
    objects = [[], [], [_box("fall", 0.9)], [_box("no-helmet", 0.5)], []]
    rig = _rig(frames, pose=pose, objects=objects)

    rig.run()

    assert _written_indices(rig.sink) == [0, 1, 2, 3, 4]
    assert _writes(rig.sink) == list(zip(frames, pose, objects, strict=True))


def test_ppe_observe_called_exactly_once_per_frame() -> None:
    # The tracker closes windows on elapsed frame time, so a frame it is not told about
    # is a gap it cannot see. Once per frame, in order, monotonic.
    frames = _frames(5)
    rig = _rig(
        frames,
        pose=[NOBODY, _pose_of(make_person()), NOBODY, NOBODY, _pose_of(make_person())],
        objects=[[_box("no-jacket", 0.7)], [], [], [_box("no-helmet", 0.7)], []],
    )

    rig.run()

    assert [frame_time_ms for frame_time_ms, _ in rig.ppe.observations] == [0, 100, 200, 300, 400]


# --------------------------------------------------------------------------
# Label mapping
# --------------------------------------------------------------------------


def test_label_to_event_type_mapping() -> None:
    # The model's class names and the engine's EventNameEnum are two different
    # vocabularies; the original compared raw strings at lines 416/426/434 and left the
    # translation implicit in five places.
    rig = _rig(
        [_frame_at(0)],
        objects=[[_box("no-helmet", 0.75), _box("no-jacket", 0.5)]],
    )

    rig.run()

    assert rig.ppe.observations == [
        (0, {EventType.NO_HELMET: 0.75, EventType.NO_JACKET: 0.5})
    ]


def test_unknown_label_is_ignored() -> None:
    # `best.pt` also emits the positive classes. A KeyError here would take the frame
    # loop down over a detection the detector does not act on, and the tracker refuses
    # any type it does not track, so an unknown label must never reach it.
    rig = _rig([_frame_at(0)], objects=[[_box("helmet", 0.95)]])

    rig.run()

    assert rig.ppe.observations == [(0, {})]
    assert _written_indices(rig.sink) == [0]


def test_multiple_violation_boxes_collapse_to_max_confidence() -> None:
    # Three bare heads are one NO_HELMET window, and what it is worth is the strongest
    # evidence for it. The original summed every box into sumHelmet/numHelmet and never
    # reset them, so it published a session-long running mean (bug #6).
    rig = _rig(
        [_frame_at(0)],
        objects=[[_box("no-helmet", 0.7), _box("no-helmet", 0.9)]],
    )

    rig.run()

    assert rig.ppe.observations == [(0, {EventType.NO_HELMET: 0.9})]


def test_fall_never_enters_the_ppe_tracker() -> None:
    # FALL is countable and has no window; `PpeViolationTracker.observe` raises on any
    # type outside `tracked`, so routing it there would stop the frame loop.
    rig = _rig(
        [_frame_at(0)],
        objects=[[_box("fall", 0.9), _box("no-helmet", 0.5)]],
    )

    rig.run()

    assert rig.ppe.observations == [(0, {EventType.NO_HELMET: 0.5})]


# --------------------------------------------------------------------------
# Fall throttling
# --------------------------------------------------------------------------


def test_fall_published_when_throttle_allows() -> None:
    # confidencePercentage is the box's own confidence. The original published
    # `row[7]`/`row[11]`, a keypoint visibility score, for its gesture events (bugs
    # #5/#7); the FALL branch is the one place a confidence must not be second-guessed,
    # because every FALL mails every user in the engine's database.
    rig = _rig([_frame_at(0)], objects=[[_box("fall", 0.77)]])

    rig.run()

    assert rig.publisher.events == [
        DetectionEvent(
            event_type=EventType.FALL,
            start_time_ms=0,
            confidence=0.77,
            camera_name=CAMERA,
            time_period_ms=None,
        )
    ]


def test_fall_suppressed_when_throttle_denies() -> None:
    # A single fall is detected on 19 consecutive frames of the baseline clip. Being
    # suppressed must cost the frame nothing else: the original's throttle lived in a
    # loop variable and the whole branch sat behind line 310's `continue`.
    throttle = FallThrottle(FALL_COOLDOWN_MS)
    assert throttle.allow(0) is True, "arming the throttle so the frame below is inside it"

    rig = _rig(
        [_frame_at(1000)],
        objects=[[_box("fall", 0.9), _box("no-helmet", 0.5)]],
        fall_throttle=throttle,
    )

    rig.run()

    assert rig.publisher.events == []
    assert rig.ppe.observations == [(1000, {EventType.NO_HELMET: 0.5})]
    assert _written_indices(rig.sink) == [0]


# --------------------------------------------------------------------------
# Person wiring
# --------------------------------------------------------------------------


def test_gesture_detector_called_once_per_person_with_its_box_conf() -> None:
    # The original indexed its per-person state by position in YOLO's output and wrapped
    # that index against `numberOfPerson`, which is a *keypoint* count of 17 (bugs #2/#3),
    # so slot 0's history routinely belonged to a different human. And it published a
    # keypoint visibility score as the event confidence; the box confidence is the number
    # that belongs to the detection.
    people = [
        make_person(hip_angle_deg=170.0, detection_confidence=0.55),
        make_person(hip_angle_deg=120.0, detection_confidence=0.71),
        make_person(hip_angle_deg=90.0, detection_confidence=0.93),
    ]
    rig = _rig([_frame_at(4200)], pose=[_pose_of(*people)])

    rig.run()

    assert [frame_time_ms for frame_time_ms, _ in rig.gestures.updates] == [4200, 4200, 4200]
    assert [observation.person_id for _, observation in rig.gestures.updates] == [0, 1, 2]
    assert [observation.detection_confidence for _, observation in rig.gestures.updates] == [
        0.55,
        0.71,
        0.93,
    ]
    assert [tuple(observation.keypoints_xy) for _, observation in rig.gestures.updates] == [
        tuple(person.keypoints_xy) for person in people
    ]
    assert [tuple(observation.keypoint_conf) for _, observation in rig.gestures.updates] == [
        tuple(person.keypoint_conf) for person in people
    ]


def test_publish_order_is_deterministic() -> None:
    # The order is: FALL, then gesture events, then PPE window closures.
    #
    # `KafkaEventPublisher.publish` flushes after every send, so publish order is
    # durability order -- whatever has already gone is what survives the process dying
    # or the broker dropping mid-frame. A gesture losing an event costs a statistic; a
    # FALL losing one is the system failing at the thing it exists for, and it is also
    # the event that mails every user in the engine's database.
    #
    # Processing the frame reads people before boxes and would put the gestures first,
    # but that order is an artifact of how the loop happens to read a frame, while
    # urgency is a requirement. Pinned here so that tidying the publish order back into
    # processing order cannot happen without seeing what it trades away -- and fixed at
    # all because the original published from five separate call sites in whatever order
    # the branches fell, so a run's transcript was never reproducible.
    front_bend = DetectionEvent(
        event_type=EventType.FRONT_BEND,
        start_time_ms=800,
        confidence=0.9,
        camera_name=CAMERA,
        time_period_ms=None,
    )
    no_helmet = DetectionEvent(
        event_type=EventType.NO_HELMET,
        start_time_ms=100,
        confidence=0.5,
        camera_name=CAMERA,
        time_period_ms=400,
    )
    fall = DetectionEvent(
        event_type=EventType.FALL,
        start_time_ms=800,
        confidence=0.64,
        camera_name=CAMERA,
        time_period_ms=None,
    )

    rig = _rig(
        [_frame_at(800)],
        pose=[_pose_of(make_person())],
        objects=[[_box("fall", 0.64)]],
        gesture_returns=[[front_bend]],
        observe_returns=[[no_helmet]],
    )

    rig.run()

    assert rig.publisher.events == [fall, front_bend, no_helmet]


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


def test_run_stops_when_should_stop_returns_true() -> None:
    # The original's only exit was `cv2.waitKey(1) == ord("q")` -- a keypress on a
    # machine with a display -- so a headless rig could not be asked to stop at all.
    stop = StopAfter(3)
    frames = _frames(10)
    rig = _rig(frames, should_stop=stop)

    rig.run()

    assert rig.pose_model.call_count == 3
    assert _written_indices(rig.sink) == [0, 1, 2]
    assert len(rig.ppe.observations) == 3


def test_run_flushes_the_tracker_on_shutdown() -> None:
    # The original ran nothing after its frame loop, so a violation still open at
    # shutdown was detected and then silently dropped. Real tracker here: the point is
    # that the open window becomes a published event, not merely that flush was called.
    frames = [_frame_at(0, index=0), _frame_at(100, index=1)]
    rig = _rig(
        frames,
        objects=[[_box("no-helmet", 0.5)], [_box("no-helmet", 0.75)]],
        ppe_tracker=PpeViolationTracker(camera_name=CAMERA, grace_ms=GRACE_MS),
    )

    rig.run()

    assert rig.publisher.events == [
        DetectionEvent(
            event_type=EventType.NO_HELMET,
            start_time_ms=0,
            confidence=0.625,
            camera_name=CAMERA,
            time_period_ms=100,
        )
    ]


def test_run_closes_source_sink_and_publisher() -> None:
    # Three resources, one shutdown. The original released the capture and the producer
    # on the normal path only, and never on the failure path.
    rig = _rig(_frames(2))

    rig.run()

    assert rig.source.close_count == 1
    assert rig.sink.close_count == 1
    assert rig.publisher.closed is True


def test_everything_closed_when_the_source_raises() -> None:
    # A camera unplugged mid-run raises out of the read. Without a try/finally that is a
    # leaked device handle and a Kafka producer abandoned with events still buffered.
    failure = RuntimeError("camera disconnected")
    source = ExplodingFrameSource(_frames(1), failure)
    rig = _rig(_frames(1), source=source)

    with pytest.raises(RuntimeError) as raised:
        rig.run()

    assert raised.value is failure
    assert _written_indices(rig.sink) == [0]
    assert rig.source.close_count == 1
    assert rig.sink.close_count == 1
    assert rig.publisher.closed is True


def test_frame_level_exception_does_not_kill_the_loop(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # One malformed frame must not end a safety detector's run -- and must not be
    # swallowed either, which is the trade this codebase makes everywhere else.
    frames = _frames(5)
    failure = ValueError("keypoint tensor was empty")
    pose_model = ExplodingPoseModel([NOBODY, failure, NOBODY, NOBODY, NOBODY])
    rig = _rig(frames, pose_model=pose_model, objects=[[] for _ in frames])

    with caplog.at_level(logging.ERROR, logger=PIPELINE_LOGGER):
        rig.run()

    assert _written_indices(rig.sink) == [0, 2, 3, 4]
    assert rig.pose_model.call_count == 5
    assert [(record.name, record.levelno) for record in caplog.records] == [
        (PIPELINE_LOGGER, logging.ERROR)
    ]
    assert rig.source.close_count == 1


def test_empty_source_runs_and_closes_cleanly() -> None:
    # A video file that is already at its end, or a camera that opened and returned
    # nothing. No frames means no writes, no events and no exception -- and still a
    # complete shutdown.
    rig = _rig([])

    rig.run()

    assert rig.pose_model.call_count == 0
    assert rig.sink.writes == []
    assert rig.publisher.events == []
    assert rig.source.close_count == 1
    assert rig.sink.close_count == 1
    assert rig.publisher.closed is True


# --------------------------------------------------------------------------
# Time discipline
# --------------------------------------------------------------------------


def test_rules_use_frame_timestamp_not_the_clock() -> None:
    # Every original event was stamped `int(time.time() * 1000)` at the moment of
    # publication rather than the moment of observation, which is both wrong under any
    # buffering and untestable without sleeping. The clock here sits at 999000000 ms, so
    # a clock-derived stamp cannot pass by coincidence.
    frames = [_frame_at(1000, 0), _frame_at(2000, 1), _frame_at(3000, 2)]
    rig = _rig(
        frames,
        objects=[[_box("fall", 0.8)], [_box("fall", 0.8)], [_box("fall", 0.8)]],
        fall_throttle=FallThrottle(0),
    )

    rig.run()

    assert [event.start_time_ms for event in rig.publisher.events] == [1000, 2000, 3000]
    assert [frame_time_ms for frame_time_ms, _ in rig.ppe.observations] == [1000, 2000, 3000]


def test_shutdown_flush_uses_the_injected_clock() -> None:
    # The one reading that cannot come from a frame: the loop has ended, so there is no
    # frame left to take it from. It still must not come from `time.time()`.
    rig = _rig(_frames(2), clock_ms=CLOCK_MS)

    rig.run()

    assert rig.ppe.flush_calls == [CLOCK_MS]


def test_pipeline_imports_no_cv2_ultralytics_kafka_or_time() -> None:
    # `tests/test_architecture.py` covers the CV stack for the whole package; `time` is
    # added here because a stray `time.time()` is exactly how the original's timestamps
    # became untestable. The whole AST is walked, not just its body, so an import
    # deferred into a function body is caught too.
    assert PIPELINE_SOURCE.is_file(), f"pipeline module not found at {PIPELINE_SOURCE}"

    roots: set[str] = set()
    for node in ast.walk(ast.parse(PIPELINE_SOURCE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])

    assert roots & FORBIDDEN_IMPORTS == set(), (
        f"pipeline.py imports {sorted(roots & FORBIDDEN_IMPORTS)}. The frame loop takes "
        "every timestamp from the frame and every heavy dependency through an injected "
        "collaborator; importing any of these puts the untestable original back."
    )
