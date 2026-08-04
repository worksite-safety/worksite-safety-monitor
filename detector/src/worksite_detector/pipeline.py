"""The frame loop: one linear path per frame, whatever the models did or did not find.

This module replaces ``aiModule.py`` lines 280-535, and its shape is a reply to one line
of them. Line 310::

    if results[0].keypoints.shape[1] == 0:
        ...
        continue

skips the entire rest of the frame whenever the pose model found nobody, and everything
that matters sits inside the block it jumps over: the PPE boxes read at line 411, the FALL
branch at 434, the violation flags, and the ``imwrite`` at 525 that feeds the web app's
preview.

**The fall that was lost.** On the baseline recording (``tests/data/baseline/PROVENANCE.md``)
there are falls at 15733 ms and 24066 ms. The pose model found nobody on the first of them
-- a person lying on the ground is precisely what a pose model is worst at -- so line 310
skipped the frame and the original published only the second. The incident was reported
**8.3 seconds late** and the first fall vanished with nothing logged. The skip is aimed,
without meaning to be, at the one event this system exists to catch.

**The preview that froze.** The same ``continue`` skips the frame write, so
``output_image.jpg`` stops being rewritten on person-free frames. The engine serves that
single file and the browser polls it every 100 ms, so an operator sees a still picture and
has nothing to distinguish it from a working camera.

Both have one cure, and it is the whole design of this module: **no early exit**. Every
frame runs the same stages in the same order and reaches the tracker and the sink, whatever
was or was not detected. A person-free frame is an observation like any other -- it is what
eventually closes a PPE window when a worker walks out of shot -- and skipping the stages
that follow it saves nothing worth having, since the model call has already been paid for.
A future reader will see stages that provably do nothing on an empty frame and be tempted
to jump over them as an optimisation. That optimisation is line 310, and it cost a fall.

The decisions this module makes, each pinned by ``tests/test_pipeline.py``:

* **Publish order within a frame is FALL, then gestures, then PPE window closures.**
  ``KafkaEventPublisher.publish`` flushes after every send, so publish order is durability
  order: whatever has already gone is what survives the process being killed or the broker
  dropping mid-frame. A gesture losing an event costs a statistic; a FALL losing one is the
  system failing at its purpose, and it is also the event that mails every user in the
  engine's database. Processing reads people before boxes and would put gestures first, but
  that order is an artifact of how a frame is read, whereas urgency is a requirement.
* **``should_stop`` is consulted once before each frame**, before the source is read rather
  than after: a stop that still costs one more frame -- and one more blocking camera read --
  is not a stop.
* **Every timestamp comes from the frame; the clock is read exactly once, at shutdown.**
  The original stamped every event ``int(time.time() * 1000)`` at the moment of publication
  rather than of observation, which is wrong under any buffering and untestable without
  sleeping. The shutdown flush is the one reading no frame can supply, because the loop has
  ended, and it still comes from the injected clock.
* **A frame whose stage raises is abandoned whole**, costing one ERROR record, and the loop
  survives it. Nothing is published for it and nothing is written for it: a half-annotated
  frame is worse than a visibly missing one, because the operator cannot tell it from a
  fresh one -- which is the confusion the frozen-preview defect already creates. Ending a
  safety detector's run over one malformed frame is the failure shape of line 310 again.
* **A failing frame *source* is fatal.** There are no further frames to read, so continuing
  would spin; it propagates, through a ``finally`` that flushes the tracker and closes every
  collaborator exactly once. The original released its capture and its producer on the
  normal path only.

Two questions the tests deliberately leave open, answered here:

* **Several ``fall`` boxes on one frame collapse to the strongest**, and the throttle is
  consulted once per frame rather than once per box. A FALL is an event about a frame, not
  about a rectangle: two boxes are two views of at most one incident, and asking the
  throttle twice would make the number of published FALLs depend on how many rectangles the
  model happened to draw. The same collapse applies to the PPE labels, where three bare
  heads are one ``NO_HELMET`` window worth the strongest evidence for it.
* **``forget`` is never called.** ``GestureDetector`` keys its state by a person id from a
  tracker, and this module has no tracker: the id it supplies is the person's position in
  one frame's pose output, so no id outlives the frame that produced it. Forgetting the ids
  absent from the current frame would therefore discard a half-completed gesture every time
  a worker was briefly missed, which is the silent loss ``pose_rules`` refuses by leaving
  removal to the caller that knows. The state that accumulates is one entry per positional
  slot, bounded by the largest crowd ever seen in a single frame. An adapter that grows a
  real tracker gets the id -- and the ``forget`` call -- at the same time.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Protocol

from worksite_detector.events import DetectionEvent, EventType
from worksite_detector.pose_rules import PersonObservation
from worksite_detector.publisher import EventPublisher

# `worksite_detector.pipeline`, which is the name an operator raises or silences
# independently of the rest of the detector.
_LOGGER = logging.getLogger(__name__)

#: The PPE model's class names, which are not the engine's event names. The original
#: compared the raw strings at lines 416, 426 and 434 and left the translation implicit in
#: five places; this is the single place the two vocabularies meet. `best.pt` also emits the
#: positive classes (`helmet`, `jacket`), and a label absent from here is ignored rather
#: than raising -- an unmapped detection is one the detector does not act on, not a reason
#: to lose the frame it arrived on.
_EVENT_TYPE_BY_LABEL: Final[Mapping[str, EventType]] = MappingProxyType(
    {
        "no-helmet": EventType.NO_HELMET,
        "no-jacket": EventType.NO_JACKET,
        "fall": EventType.FALL,
    }
)


@dataclass(frozen=True)
class Frame:
    """One frame read from the source, with the time it was taken.

    ``image`` is opaque by contract: it is handed to the models and to the sink and is
    never looked inside here, which is what keeps this module free of the CV stack (see
    ``tests/test_architecture.py``). ``timestamp_ms`` is the frame's own time in
    milliseconds since the epoch, and it -- never a clock reading -- stamps every event
    derived from this frame. ``index`` counts frames from the start of the run and exists
    for logs and for the sink; nothing decides anything from it.
    """

    image: Any
    timestamp_ms: int
    index: int


@dataclass(frozen=True)
class PoseDetection:
    """One frame's pose output: three index-aligned rows, one entry per person.

    Empty on a frame the model found nobody in -- 278 of the baseline clip's 986 frames,
    and the case that the original skipped the rest of the frame over.

    Attributes:
        keypoints_xy: Per person, 17 ``(x, y)`` pairs in COCO order, in image pixels. A
            keypoint the model did not find arrives as ``(0.0, 0.0)``.
        keypoint_conf: Per person, 17 visibility scores, index-aligned with the keypoints.
        box_conf: Per person, the confidence of the person *box*. This is what is published
            as an event's ``confidencePercentage``; the original published a keypoint
            visibility score instead.
    """

    keypoints_xy: list[list[tuple[float, float]]]
    keypoint_conf: list[list[float]]
    box_conf: list[float]


@dataclass(frozen=True)
class ObjectDetection:
    """One box from the PPE/fall model.

    ``label`` is the raw model class -- ``"no-helmet"``, ``"no-jacket"``, ``"fall"`` -- and
    not the engine's event name; ``confidence`` is a fraction in [0, 1], as everywhere in
    this package. ``box`` is ``(x1, y1, x2, y2)`` in image pixels: no rule reads it, and it
    is carried for the annotating sink to draw.
    """

    label: str
    confidence: float
    box: tuple[int, int, int, int]


class _FrameSource(Protocol):
    """Where frames come from: a camera, a video file, a recorded trace."""

    def __iter__(self) -> Iterator[Frame]: ...

    def close(self) -> None:
        """Release the capture. Called from the pipeline's ``finally``."""


class _PoseModel(Protocol):
    """The pose model, called with one frame's image.

    In production an adapter around ``YOLO("yolov8s-pose.pt")`` that turns its tensors into
    the plain rows of a ``PoseDetection``; the tensors themselves never cross this seam.
    """

    def __call__(self, image: Any) -> PoseDetection: ...


class _ObjectModel(Protocol):
    """The PPE/fall model, called with one frame's image.

    In production an adapter around ``YOLO("best.pt")``. Its output is passed through to the
    sink unchanged, so a frame is annotated from its own detections and never from the last
    frame that had any.
    """

    def __call__(self, image: Any) -> Sequence[ObjectDetection]: ...


class _FrameSink(Protocol):
    """Where the annotated frame goes -- in production, ``output_image.jpg``."""

    def write(
        self, frame: Frame, pose: PoseDetection, objects: Sequence[ObjectDetection]
    ) -> None:
        """Render one frame. Both detection results are passed because the sink draws
        the skeletons and the violation boxes, and the whole ``Frame`` because a
        timestamp or an index is the sink's to stamp or log."""

    def close(self) -> None:
        """Release whatever the sink holds. Called from the pipeline's ``finally``."""


class _GestureDetector(Protocol):
    """The countable-gesture state machine; ``pose_rules.GestureDetector`` in production."""

    def update(
        self, frame_time_ms: int, observation: PersonObservation
    ) -> Sequence[DetectionEvent]: ...


class _PpeTracker(Protocol):
    """The periodic-violation windows; ``ppe_rules.PpeViolationTracker`` in production."""

    def observe(
        self, frame_time_ms: int, violations: Mapping[EventType, float]
    ) -> Sequence[DetectionEvent]: ...

    def flush(self, now_ms: int) -> Sequence[DetectionEvent]: ...


class _FallThrottle(Protocol):
    """The FALL rate limiter; ``ppe_rules.FallThrottle`` in production."""

    def allow(self, now_ms: int) -> bool: ...


class Pipeline:
    """Runs one camera's frame loop until the source ends or ``should_stop`` says so.

    Every collaborator is injected, which is what makes the loop testable at all: the
    original built a ``VideoCapture``, two ``YOLO`` models and a ``KafkaProducer`` at module
    scope, so importing it needed a camera, a GPU and a broker.

    One instance per camera, single-threaded. It owns no state of its own beyond the
    collaborators it was handed -- the rule objects hold theirs -- and it is not reusable:
    ``run`` closes the source, the sink and the publisher on its way out.
    """

    def __init__(
        self,
        *,
        frame_source: _FrameSource,
        pose_model: _PoseModel,
        object_model: _ObjectModel,
        sink: _FrameSink,
        publisher: EventPublisher,
        gesture_detector: _GestureDetector,
        ppe_tracker: _PpeTracker,
        fall_throttle: _FallThrottle,
        clock: Callable[[], int],
        should_stop: Callable[[], bool],
        camera_name: str,
    ) -> None:
        """Wire one camera's loop.

        Keyword-only because eleven positional collaborators, most of them callables, are
        indistinguishable at a call site and two of them could be swapped in silence.

        ``clock`` returns milliseconds since the epoch and is read exactly once, by the
        shutdown flush; every other time in the run comes from the frame that produced it.
        ``should_stop`` is polled once before each frame, and is how a headless rig is asked
        to stop -- the original's only exit was ``cv2.waitKey(1) == ord("q")``, a keypress on
        a machine with a display. ``camera_name`` is published verbatim on every event and is
        how the dashboard attributes a violation to a site.

        Nothing is validated here. The collaborators are structural, so a missing method is
        an ``AttributeError`` naming it at the seam that used it, which is more useful than
        a constructor rejecting an object for a method it might never call.
        """
        self._frame_source = frame_source
        self._pose_model = pose_model
        self._object_model = object_model
        self._sink = sink
        self._publisher = publisher
        self._gesture_detector = gesture_detector
        self._ppe_tracker = ppe_tracker
        self._fall_throttle = fall_throttle
        self._clock = clock
        self._should_stop = should_stop
        self._camera_name = camera_name

    def run(self) -> None:
        """Process frames until the source is exhausted or the run is asked to stop.

        Returns normally on either. Anything raised by the frame *source* propagates, and
        the shutdown in the ``finally`` runs either way: the tracker's open windows are
        flushed and published, and the source, the sink and the publisher are each closed
        exactly once. A failure inside a single frame is handled per frame and never reaches
        here; see ``_process``.
        """
        try:
            self._read_frames()
        finally:
            self._shut_down()

    def _read_frames(self) -> None:
        """Pull frames one at a time, checking the stop signal before each read."""
        frames = iter(self._frame_source)
        while not self._should_stop():
            try:
                frame = next(frames)
            except StopIteration:
                return
            self._handle_frame(frame)

    def _handle_frame(self, frame: Frame) -> None:
        """Process one frame, and survive it failing.

        ``Exception`` and not ``BaseException``, so a Ctrl+C during a frame still stops the
        detector instead of being logged as a bad frame. The record carries the traceback
        because the cause is inside a collaborator -- a model, a rule, the sink -- and
        without the frames there is nothing to point at; the frame's index and time are in
        the message so it can be found again in the recording.
        """
        try:
            self._process(frame)
        except Exception:
            _LOGGER.exception(
                "frame %d at %d ms was abandoned: nothing was published for it and no "
                "annotated frame was written, so the preview holds the previous frame. "
                "The loop continues with the next one.",
                frame.index,
                frame.timestamp_ms,
            )

    def _process(self, frame: Frame) -> None:
        """The whole of one frame, in one straight line and with no early exit.

        The order of the stages is the order the frame is read in -- people, then boxes --
        and it is deliberately not the order events are published in; see the module
        docstring. The sink write is last so that "a failed frame writes nothing" holds
        without a second decision: any stage that raises has already skipped it.
        """
        pose = self._pose_model(frame.image)
        objects = self._object_model(frame.image)

        gesture_events = self._gestures_of(frame, pose)
        fall_confidence, violations = _collapse_boxes(objects)

        fall_events: list[DetectionEvent] = []
        # Once per frame, not once per box, and only where there is something to throttle:
        # `allow` re-arms itself when it says yes, so asking it about a frame with no fall
        # on it would move the cooldown for a fall nobody detected.
        if fall_confidence is not None and self._fall_throttle.allow(frame.timestamp_ms):
            fall_events.append(
                DetectionEvent(
                    event_type=EventType.FALL,
                    start_time_ms=frame.timestamp_ms,
                    confidence=fall_confidence,
                    camera_name=self._camera_name,
                    # Countable: no window and no duration. `/event/periodic-events` SUMS
                    # timePeriod over whatever carries one.
                    time_period_ms=None,
                )
            )

        # Every frame, including the clean and the person-free ones: a frame the tracker is
        # not told about is a gap it cannot see, and it is a clean frame that closes a
        # violation the worker ended by walking out of shot.
        ppe_events = self._ppe_tracker.observe(frame.timestamp_ms, violations)

        self._publish(fall_events)
        self._publish(gesture_events)
        self._publish(ppe_events)

        self._sink.write(frame, pose, objects)

    def _gestures_of(self, frame: Frame, pose: PoseDetection) -> list[DetectionEvent]:
        """Feed every person of this frame to the gesture detector, in model order.

        The three pose rows are zipped strictly: they are index-aligned by construction, and
        a short one means the adapter sliced the model's output wrongly. Failing here costs
        one frame and names its cause, where reading past the end of the shorter row would
        hand one person another's confidence for the rest of the run.

        The person id is the person's position in this frame's output, which is an identity
        only within the frame -- see the module docstring on ``forget``.
        """
        events: list[DetectionEvent] = []
        for person_id, (keypoints_xy, keypoint_conf, box_conf) in enumerate(
            zip(pose.keypoints_xy, pose.keypoint_conf, pose.box_conf, strict=True)
        ):
            observation = PersonObservation(
                person_id=person_id,
                keypoints_xy=tuple(keypoints_xy),
                keypoint_conf=tuple(keypoint_conf),
                detection_confidence=box_conf,
            )
            events.extend(self._gesture_detector.update(frame.timestamp_ms, observation))
        return events

    def _publish(self, events: Iterable[DetectionEvent]) -> None:
        """Hand each event to the publisher, in the order given.

        The publisher's contract is that it does not raise on a transport failure, so this
        is not guarded: an exception from here is a bug in a publisher, not a broker being
        down, and it should surface as one.
        """
        for event in events:
            self._publisher.publish(event)

    def _shut_down(self) -> None:
        """Flush what is still open, then close every collaborator exactly once.

        Runs on the failure path too, which is the point: the original ran nothing after its
        frame loop, so a violation still in progress at shutdown was detected and then
        dropped in silence, and anything raising out of the loop leaked the camera handle
        and abandoned a producer with events still buffered.

        Each step is isolated. A flush that fails must still leave the resources released,
        and a close that fails must not take the other two with it -- and neither may mask
        the source failure that may be propagating through this ``finally`` right now, which
        is the one an operator has to see.
        """
        try:
            # The one time reading the loop cannot take from a frame, because there is no
            # frame left; the tracker measures each window to its own last frame regardless,
            # so a slow teardown cannot stretch a duration.
            self._publish(self._ppe_tracker.flush(self._clock()))
        except Exception:
            _LOGGER.exception(
                "the shutdown flush failed, so any violation still open was lost; "
                "closing the detector's resources anyway"
            )

        # Source first so no further frame is read, then the sink, then the publisher last,
        # so the flushed events above are away before the connection goes.
        for name, close in (
            ("frame source", self._frame_source.close),
            ("frame sink", self._sink.close),
            ("event publisher", self._publisher.close),
        ):
            try:
                close()
            except Exception:
                _LOGGER.exception("closing the %s failed; the others are still closed", name)


def _collapse_boxes(
    objects: Iterable[ObjectDetection],
) -> tuple[float | None, dict[EventType, float]]:
    """Read one frame's boxes into a fall confidence and one confidence per violated type.

    Both collapses take the strongest box, because a frame states *whether* a violation is
    present and how good the evidence for it is: three bare heads are one ``NO_HELMET``
    window, and what it is worth is the best look the model got. The original summed every
    box into ``sumHelmet``/``numHelmet`` and never reset them, so every event after the
    first reported a session-long running mean.

    FALL is returned separately and never reaches the tracker: it is countable and has no
    window, and ``PpeViolationTracker.observe`` refuses any type outside the ones it tracks,
    so routing it there would stop the frame loop. A mapped type that is neither FALL nor
    periodic cannot occur -- ``_EVENT_TYPE_BY_LABEL`` holds exactly three labels -- and is
    dropped rather than guessed at, which is the same answer as for an unknown label.
    """
    fall_confidence: float | None = None
    violations: dict[EventType, float] = {}

    for detection in objects:
        event_type = _EVENT_TYPE_BY_LABEL.get(detection.label)
        if event_type is EventType.FALL:
            fall_confidence = _strongest(fall_confidence, detection.confidence)
        elif event_type is not None and event_type.is_periodic:
            violations[event_type] = _strongest(
                violations.get(event_type), detection.confidence
            )

    return fall_confidence, violations


def _strongest(current: float | None, candidate: float) -> float:
    """``candidate`` if nothing has been seen yet, otherwise the larger of the two."""
    return candidate if current is None else max(current, candidate)
