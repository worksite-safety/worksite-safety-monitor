"""The differential: the rewritten detector and the original, over the same 986 frames.

Every other test in this suite says what the new code *should* do. This one says what it
does **differently from the code it replaces**, on real worksite footage, and it is the
only test that can tell an intended behaviour change from an accident.

How the two runs are made comparable
------------------------------------
`tests/data/baseline/trace.jsonl.gz` holds one JSON record per frame: the pose model's
keypoints, the per-keypoint confidences, the person-box confidences and the PPE/fall
boxes, captured once from `Baumit İnşaat Alanı.mp4` (see `PROVENANCE.md`). Both runs are
driven from **the same in-memory list of those records**, in the same order:

* `legacy_oracle.replay(records)` reads the records directly -- it is a transcription of
  `aiModule.py` lines 312-512 with the producer, `time.time()` and `datetime.now()`
  substituted out, and nothing else.
* the real `Pipeline` is handed a frame source that yields `Frame(image=record, ...)`,
  and two fake models that read that same record back out of `frame.image`. The models
  therefore cannot return anything the oracle did not also see, because the record object
  they read *is* the record the oracle read -- identity, not a copy.

Everything else is production code: `GestureDetector`, `PpeViolationTracker`,
`FallThrottle` and `InMemoryEventPublisher`, wired from `Config()` defaults, whose values
are the original's own constants. The only test doubles are the frame source, the two
models, the sink, and a spy that records what the real gesture detector was handed and
then delegates to it.

Events are compared per type by **count**, by the **ordered frame indices** they were
emitted on, and by the field tuple **(start_time_ms, confidence, time_period_ms)** --
never as raw JSON, which would drown the signal in key ordering and in the `isProcessed`
spelling.

What the differential actually found
------------------------------------
Two of the expected differences did not appear, and both are recorded here as they were
measured rather than argued away:

1. **FALL does not go from 1 to 2. It stays at 1 and moves.** The falls are at 15733 ms
   and 24066 ms. The original missed the first (its frame has no detectable person, so
   line 310's `continue` skipped the whole frame) and published the second. The rewrite
   sees the first -- and `FallThrottle`, at the original's own 3-minute cooldown, then
   suppresses the second 8333 ms later along with the other 17 detections. One fall is
   published either way; the rewrite publishes the *earlier* one, 8.3 seconds sooner.
   Reporting both would need a cooldown shorter than the gap between two incidents, which
   is a tuning decision this differential cannot make and does not hide.

2. **ARMS_UP and FRONT_BEND stay at zero, and the footage is why.** Measured over all 1114
   person-frames: the shoulder angle ARMS_UP watches never exceeds **121.5 deg** against a
   `relaxing` threshold of 140, so no arm-raise ever completes; the hip angle FRONT_BEND
   watches never falls below **156.4 deg** against a `maintaining` threshold of 130, so no
   bend ever starts. The latch that could not re-arm was a real defect, but on this clip it
   was never the binding constraint -- there is no completed gesture in the footage for
   either state machine to miss. The gates passing 964 and 811 times says a limb was
   *visible*, not that a gesture *happened*. Every gesture assertion in this project is
   therefore synthetic, and this file cannot promote any of them.

A third finding is about the consumer rather than the producer, and is recorded in
`DIFFERENTIAL.md`: `timePeriod` is now milliseconds, but the engine still compares it
against `event.fall.threshold.value`, which is the literal `3` in
`engine/src/main/resources/application.yml`. Under the intended 3000 ms reading exactly
one of the four NO_JACKET windows is stored; under the engine as actually deployed,
three are. Both are asserted below so the gap cannot close by accident.
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from worksite_detector.config import Config
from worksite_detector.events import DetectionEvent, EventType
from worksite_detector.geometry import joint_angle
from worksite_detector.pipeline import Frame, ObjectDetection, Pipeline, PoseDetection
from worksite_detector.pose_rules import GestureDetector, PersonObservation
from worksite_detector.ppe_rules import FallThrottle, PpeViolationTracker
from worksite_detector.publisher import InMemoryEventPublisher

BASELINE_DIR = Path(__file__).resolve().parent / "data" / "baseline"
TRACE = BASELINE_DIR / "trace.jsonl.gz"
ORACLE = BASELINE_DIR / "legacy_oracle.py"
FROZEN_EVENTS = BASELINE_DIR / "baseline_events.jsonl"

#: `Args.input` in the original, and `CameraConfig.source`'s default here. Both runs must
#: publish the same camera name or every event differs for a reason nobody cares about.
CAMERA = "0"

#: What `RawEventService.listener` means to enforce: a periodic event is stored only if its
#: duration is strictly over three seconds.
ENGINE_PERIODIC_THRESHOLD_MS = 3000

#: What `engine/src/main/resources/application.yml` actually configures --
#: `event.fall.threshold.value: 3`, compared against `timePeriod` with no unit conversion.
#: Correct when the producer sent seconds; the rewrite sends milliseconds.
ENGINE_CONFIGURED_THRESHOLD = 3

#: Every event type either run can produce, in a fixed order so the comparison table below
#: is stable and a type that vanished shows up as a zero rather than as a missing row.
EVENT_TYPES = ("FALL", "ARMS_UP", "FRONT_BEND", "NO_HELMET", "NO_JACKET")

#: Emitted by the shutdown flush, after the last frame; not by any frame.
SHUTDOWN = -1


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def _load_trace() -> list[dict]:
    with gzip.open(TRACE, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _load_oracle() -> Any:
    """Import `legacy_oracle.py` by path -- `tests/data/baseline` is a data directory,
    not an importable package, and `tests/test_baseline_oracle.py` keeps it that way."""
    spec = importlib.util.spec_from_file_location("legacy_oracle", ORACLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# The doubles: a frame source, two models, a sink, and a spy on the real detector.
#
# Nothing here decides anything. The models are pure projections of the trace record they
# are handed, which is what makes "the two runs saw the same input" a fact about object
# identity rather than a claim about two loaders agreeing.
# --------------------------------------------------------------------------


class _TraceFrameSource:
    """Yields one `Frame` per trace record, carrying the record itself as the image."""

    def __init__(self, records: Sequence[dict]) -> None:
        self._records = records
        self.close_count = 0

    def __iter__(self) -> Iterator[Frame]:
        for record in self._records:
            yield Frame(
                image=record,
                timestamp_ms=record["timestamp_ms"],
                index=record["index"],
            )

    def close(self) -> None:
        self.close_count += 1


class _TracePoseModel:
    """Replays the pose rows recorded for whichever frame it is handed."""

    def __init__(self) -> None:
        self.seen: list[int] = []

    def __call__(self, image: Any) -> PoseDetection:
        self.seen.append(image["index"])
        pose = image["pose"]
        return PoseDetection(
            keypoints_xy=[
                [(float(x), float(y)) for x, y in person] for person in pose["keypoints_xy"]
            ],
            keypoint_conf=[[float(c) for c in person] for person in pose["keypoint_conf"]],
            box_conf=[float(c) for c in pose["box_conf"]],
        )


class _TraceObjectModel:
    """Replays the PPE/fall boxes recorded for whichever frame it is handed."""

    def __init__(self) -> None:
        self.seen: list[int] = []

    def __call__(self, image: Any) -> list[ObjectDetection]:
        self.seen.append(image["index"])
        return [
            ObjectDetection(
                label=detection["label"],
                confidence=float(detection["confidence"]),
                box=tuple(int(value) for value in detection["box"]),  # type: ignore[arg-type]
            )
            for detection in image["objects"]
        ]


class _CheckpointSink:
    """Records which frame reached the end of the pipeline, and how many events had gone.

    `Pipeline._process` writes to the sink *last*, after publishing, so the publisher's
    length at each write is the running total of everything emitted up to and including
    that frame. That is how each event gets a frame index without wrapping the publisher
    under test -- and the write count is itself the no-early-exit proof, since the original
    skipped its own frame write on all 278 person-free frames.
    """

    def __init__(self, publisher: InMemoryEventPublisher) -> None:
        self._publisher = publisher
        self.checkpoints: list[tuple[int, int]] = []
        self.close_count = 0

    def write(
        self, frame: Frame, pose: PoseDetection, objects: Sequence[ObjectDetection]
    ) -> None:
        self.checkpoints.append((frame.index, len(self._publisher.events)))

    def close(self) -> None:
        self.close_count += 1


class _ObservationSpy:
    """The real `GestureDetector`, with a note of everything it was handed.

    Delegation, not substitution: the decisions are the production state machine's. The
    record exists because the confidence swap -- keypoint visibility to detection box --
    cannot be shown from the published events on this footage, since neither run publishes
    a gesture at all. What it *can* be shown from is the value that reached the rule.
    """

    def __init__(self, detector: GestureDetector) -> None:
        self._detector = detector
        self.observations: list[PersonObservation] = []

    def update(
        self, frame_time_ms: int, observation: PersonObservation
    ) -> list[DetectionEvent]:
        self.observations.append(observation)
        return self._detector.update(frame_time_ms, observation)


# --------------------------------------------------------------------------
# The two runs
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _NewRun:
    """Everything the rewritten detector did on the trace."""

    events: list[DetectionEvent]
    frame_indices: list[int]
    pose_calls: list[int]
    object_calls: list[int]
    sink_indices: list[int]
    observations: list[PersonObservation]
    seconds: float
    source_closed: int
    sink_closed: int
    publisher_closed: bool


@dataclass(frozen=True)
class _LegacyRun:
    """Everything the transcribed original did on the same trace."""

    events: list[dict]
    frame_indices: list[int]
    seconds: float


@dataclass(frozen=True)
class _Differential:
    """Both runs plus the records they were driven from."""

    records: list[dict]
    new: _NewRun
    legacy: _LegacyRun
    total_seconds: float = field(default=0.0)


def _run_new(records: Sequence[dict]) -> _NewRun:
    """Drive the real `Pipeline` over `records` with production rules throughout."""
    config = Config()
    publisher = InMemoryEventPublisher()
    source = _TraceFrameSource(records)
    pose_model = _TracePoseModel()
    object_model = _TraceObjectModel()
    sink = _CheckpointSink(publisher)

    spy = _ObservationSpy(
        GestureDetector(
            gestures=config.gestures,
            camera_name=CAMERA,
            keypoint_visibility=config.thresholds.keypoint_visibility,
            upright_left_idx=config.upright.left_idx,
            upright_right_idx=config.upright.right_idx,
            upright_angle=config.upright.angle_degrees,
        )
    )

    pipeline = Pipeline(
        frame_source=source,
        pose_model=pose_model,
        object_model=object_model,
        sink=sink,
        publisher=publisher,
        gesture_detector=spy,
        ppe_tracker=PpeViolationTracker(
            camera_name=CAMERA, grace_ms=config.thresholds.ppe_grace_ms
        ),
        fall_throttle=FallThrottle(cooldown_ms=config.thresholds.fall_cooldown_ms),
        # Read once, by the shutdown flush, and used to measure nothing. The last frame's
        # time is the honest reading; any value gives the same events.
        clock=lambda: records[-1]["timestamp_ms"],
        should_stop=lambda: False,
        camera_name=CAMERA,
    )

    started = time.perf_counter()
    pipeline.run()
    seconds = time.perf_counter() - started

    return _NewRun(
        events=list(publisher.events),
        frame_indices=_attribute_to_frames(sink.checkpoints, len(publisher.events)),
        pose_calls=pose_model.seen,
        object_calls=object_model.seen,
        sink_indices=[index for index, _total in sink.checkpoints],
        observations=spy.observations,
        seconds=seconds,
        source_closed=source.close_count,
        sink_closed=sink.close_count,
        publisher_closed=publisher.closed,
    )


def _attribute_to_frames(checkpoints: Sequence[tuple[int, int]], total: int) -> list[int]:
    """The frame index each event was published on, in publication order.

    `checkpoints` is `(frame index, events published so far)` at the end of each frame, so
    the events between two consecutive totals belong to the later frame. Anything after the
    last checkpoint came from the shutdown flush and is marked `SHUTDOWN`.
    """
    indices: list[int] = []
    previous = 0
    for frame_index, running_total in checkpoints:
        indices.extend([frame_index] * (running_total - previous))
        previous = running_total
    indices.extend([SHUTDOWN] * (total - previous))
    return indices


def _run_legacy(records: Sequence[dict]) -> _LegacyRun:
    """Replay the transcribed original over the same records."""
    oracle = _load_oracle()

    started = time.perf_counter()
    events = oracle.replay(records)
    seconds = time.perf_counter() - started

    return _LegacyRun(
        events=events,
        frame_indices=[_legacy_frame_index(records, event) for event in events],
        seconds=seconds,
    )


def _legacy_frame_index(records: Sequence[dict], event: dict) -> int:
    """Which frame the original emitted `event` on.

    The oracle stamps a countable event `int(_now * 1000)` where `_now` is the current
    frame's timestamp in seconds, so inverting it means applying the identical
    millisecond -> second -> millisecond round trip to every frame and looking the result
    up. That round trip is lossy on 10 of the 986 frames, which is exactly why the map is
    built through it rather than from the raw timestamps.

    Only valid for countable events; a periodic one is stamped with the *start* of its
    window rather than the frame it was published on. `test_legacy_emitted_nothing_periodic`
    is what makes that restriction safe to ignore here.
    """
    by_start = {int(record["timestamp_ms"] / 1000.0 * 1000): record["index"] for record in records}
    return by_start[event["startTime"]]


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def differential() -> _Differential:
    """Both replays, once for the whole module.

    Module-scoped because it is the same deterministic computation for every test below and
    it is the only expensive thing here; see `test_differential_is_fast_enough_to_keep`.
    """
    if not TRACE.exists():
        pytest.skip(f"baseline trace not present: {TRACE}")

    started = time.perf_counter()
    records = _load_trace()
    legacy = _run_legacy(records)
    new = _run_new(records)
    total = time.perf_counter() - started

    return _Differential(records=records, new=new, legacy=legacy, total_seconds=total)


# --------------------------------------------------------------------------
# Comparison helpers
# --------------------------------------------------------------------------


def _new_counts(run: _NewRun) -> Counter[str]:
    return Counter(event.event_type.value for event in run.events)


def _legacy_counts(run: _LegacyRun) -> Counter[str]:
    return Counter(event["eventType"] for event in run.events)


def _new_of(run: _NewRun, event_type: str) -> list[tuple[int, tuple[int, float, int | None]]]:
    """`(frame index, (start_time_ms, confidence, time_period_ms))` for one type, in order."""
    return [
        (index, (event.start_time_ms, event.confidence, event.time_period_ms))
        for index, event in zip(run.frame_indices, run.events, strict=True)
        if event.event_type.value == event_type
    ]


def _legacy_of(run: _LegacyRun, event_type: str) -> list[tuple[int, tuple[int, float, int | None]]]:
    """The same shape for the original, whose payload spells the three fields differently."""
    return [
        (
            index,
            (event["startTime"], event["confidencePercentage"], event.get("timePeriod")),
        )
        for index, event in zip(run.frame_indices, run.events, strict=True)
        if event["eventType"] == event_type
    ]


def _detections(records: Sequence[dict], label: str) -> list[tuple[int, int, float]]:
    """`(frame index, timestamp, best confidence)` for every frame carrying `label`."""
    return [
        (
            record["index"],
            record["timestamp_ms"],
            max(o["confidence"] for o in record["objects"] if o["label"] == label),
        )
        for record in records
        if any(o["label"] == label for o in record["objects"])
    ]


# --------------------------------------------------------------------------
# The baseline is the frozen file, and the two runs saw the same input
# --------------------------------------------------------------------------


def test_frozen_baseline_matches_the_oracle(differential: _Differential) -> None:
    """The file this whole differential is measured against is the file the oracle writes.

    Without this, a stale `baseline_events.jsonl` would silently redefine "what the original
    did" and every difference below would be measured from fiction.
    """
    frozen = [json.loads(line) for line in FROZEN_EVENTS.read_text(encoding="utf-8").splitlines()
              if line.strip()]

    assert differential.legacy.events == frozen, (
        "legacy_oracle.replay no longer reproduces baseline_events.jsonl. The baseline is "
        "frozen evidence: regenerate it deliberately with build_baseline.py and review the "
        "diff, never as a side effect of a test run."
    )


def test_both_runs_read_the_same_records(differential: _Differential) -> None:
    """The models cannot have invented input: they project the record the oracle read.

    Asserted by object identity, not by equality -- the pipeline's frame source carries each
    trace record through as `frame.image`, and the two fake models read it back out. There
    is no second parse of the file and no second copy to drift.
    """
    records = differential.records
    expected = [record["index"] for record in records]

    assert len(records) == 986
    assert differential.new.pose_calls == expected, (
        "the pose model was not called exactly once per trace record, in order"
    )
    assert differential.new.object_calls == expected, (
        "the object model was not called exactly once per trace record, in order"
    )


def test_the_rewrite_reaches_every_frame_and_the_original_did_not(
    differential: _Differential,
) -> None:
    """986 frames in, 986 frames all the way through -- the fix to `aiModule.py` line 310.

    The original's `continue` skipped the rest of the frame on all 278 person-free frames,
    taking the PPE boxes, the FALL branch and the preview write with it. That count is the
    size of the blind spot every difference below comes out of.
    """
    records = differential.records
    person_free = [r["index"] for r in records if not r["pose"]["keypoints_xy"]]

    assert len(person_free) == 278
    assert differential.new.sink_indices == [r["index"] for r in records], (
        "the pipeline did not reach the sink on every frame; the frozen-preview and "
        "lost-fall defects both live in exactly that gap"
    )
    assert differential.new.source_closed == 1
    assert differential.new.sink_closed == 1
    assert differential.new.publisher_closed is True


def test_legacy_emitted_nothing_periodic(differential: _Differential) -> None:
    """Nothing the original emitted carries a `timePeriod`, which is what makes the frame
    attribution above exact -- a periodic legacy event is stamped with its window start, not
    with the frame it was published on."""
    assert [e for e in differential.legacy.events if "timePeriod" in e] == []


# --------------------------------------------------------------------------
# The comparison table
# --------------------------------------------------------------------------


def test_event_counts_per_type(differential: _Differential) -> None:
    """The whole differential in one assertion: how many of each type, before and after.

    +------------+----------+-----+
    | type       | baseline | new |
    +------------+----------+-----+
    | FALL       |        1 |   1 |  same count, different incident (see below)
    | ARMS_UP    |        0 |   0 |  the footage contains no completed arm raise
    | FRONT_BEND |        0 |   0 |  the footage contains no bend below 130 deg
    | NO_HELMET  |        0 |   0 |  the trace holds no no-helmet detection at all
    | NO_JACKET  |        0 |   4 |  the headline fix: bug #1
    +------------+----------+-----+
    """
    legacy = _legacy_counts(differential.legacy)
    new = _new_counts(differential.new)

    assert [legacy.get(t, 0) for t in EVENT_TYPES] == [1, 0, 0, 0, 0]
    assert [new.get(t, 0) for t in EVENT_TYPES] == [1, 0, 0, 0, 4]

    assert len(differential.legacy.events) == 1
    assert len(differential.new.events) == 5


def test_nothing_was_emitted_after_the_last_frame(differential: _Differential) -> None:
    """No window was still open at shutdown, so every event below belongs to a real frame
    and the injected clock never reached a published field."""
    assert SHUTDOWN not in differential.new.frame_indices


# --------------------------------------------------------------------------
# NO_JACKET -- the headline fix
# --------------------------------------------------------------------------


def test_no_jacket_goes_from_never_published_to_four_windows(
    differential: _Differential,
) -> None:
    """Bug #1: 63 frames of evidence, zero events, for the life of the project.

    `controlJacket` is set False at `aiModule.py` line 409 and set False *again* at 428
    where True was meant, so the emit block at 489 is unreachable on every input. The
    rewrite has no such flag: a window opens on the first violating frame and closes when
    the type has been absent for the grace period.
    """
    jacket_frames = _detections(differential.records, "no-jacket")
    assert len(jacket_frames) == 63, "the trace no longer carries the 63 no-jacket frames"

    assert _legacy_of(differential.legacy, "NO_JACKET") == []

    emitted = _new_of(differential.new, "NO_JACKET")
    assert len(emitted) == 4

    indices = [index for index, _fields in emitted]
    assert indices == [395, 492, 563, 956]

    starts = [fields[0] for _index, fields in emitted]
    periods = [fields[2] for _index, fields in emitted]
    assert starts == [11666, 14700, 17233, 23866]
    assert periods == [0, 200, 33, 6500]

    # Every window starts on a frame that actually carried a no-jacket box, and closes
    # after the last one it absorbed -- never on a frame invented by the tracker.
    violating_ms = {timestamp for _index, timestamp, _conf in jacket_frames}
    assert set(starts) <= violating_ms

    confidences = [fields[1] for _index, fields in emitted]
    detection_confidences = [conf for _index, _ts, conf in jacket_frames]
    assert min(confidences) >= min(detection_confidences)
    assert max(confidences) <= max(detection_confidences)


def test_at_least_one_no_jacket_window_clears_the_engine_threshold(
    differential: _Differential,
) -> None:
    """Fixing bug #1 alone would still have recorded nothing; the grace window is the fix.

    The 63 violating frames arrive as 27 runs, the longest 367 ms, so closing a window on
    the first clean frame produces 63 events and not one of them survives the engine's
    3-second gate. Merged across gaps under 1500 ms they become four windows, one of which
    is 6500 ms and is stored.

    The second assertion is the same question asked of the engine **as it is actually
    configured**: `event.fall.threshold.value` is the bare integer `3`, compared against
    `timePeriod` with no unit conversion. That was three seconds while the producer sent
    seconds; against milliseconds it is three *milliseconds*, and three of the four windows
    clear it -- including a 33 ms flicker. The producer-side unit fix needs a matching
    change on the engine side, and this is where its absence is visible.
    """
    periods = [fields[2] for _index, fields in _new_of(differential.new, "NO_JACKET")]

    stored_at_3s = [p for p in periods if p is not None and p > ENGINE_PERIODIC_THRESHOLD_MS]
    assert stored_at_3s == [6500], (
        "no emitted NO_JACKET clears a 3000 ms threshold, so the fix records nothing in "
        "practice and the failure has only moved downstream into the engine"
    )

    stored_as_deployed = [p for p in periods if p is not None and p > ENGINE_CONFIGURED_THRESHOLD]
    assert stored_as_deployed == [200, 33, 6500]


def test_grace_sweep_on_this_trace_and_one_row_of_PROVENANCE_is_wrong(
    differential: _Differential,
) -> None:
    """The sweep the 1500 ms default was chosen from, re-measured with the real tracker.

    `PROVENANCE.md` and the `ppe_rules` module docstring both publish this sweep, and both
    have the **500 ms row wrong**: they say 7 windows of which 1 clears 3 seconds. Driving
    `PpeViolationTracker` itself over the trace gives **8 windows, none of which clears 3
    seconds** -- the longest is 2934 ms. Every other row matches exactly.

    The conclusion the sweep was drawn for survives and is in fact stronger: 500 ms records
    nothing, 1000 ms is the first setting that records anything at all, and 1500 ms is where
    the run collapses into one coherent 6500 ms violation. Only the number is wrong, and it
    is pinned here rather than corrected in a frozen provenance document.
    """
    jacket_frames = {ts: conf for _i, ts, conf in _detections(differential.records, "no-jacket")}

    def sweep(grace_ms: int) -> list[int]:
        tracker = PpeViolationTracker(camera_name=CAMERA, grace_ms=grace_ms)
        emitted: list[DetectionEvent] = []
        for record in differential.records:
            timestamp = record["timestamp_ms"]
            violations = (
                {EventType.NO_JACKET: jacket_frames[timestamp]}
                if timestamp in jacket_frames
                else {}
            )
            emitted.extend(tracker.observe(timestamp, violations))
        emitted.extend(tracker.flush(differential.records[-1]["timestamp_ms"]))
        return [event.time_period_ms for event in emitted if event.time_period_ms is not None]

    measured = {grace: sweep(grace) for grace in (0, 500, 1000, 1500, 2000)}
    counts = {grace: len(durations) for grace, durations in measured.items()}
    over_threshold = {
        grace: sum(1 for d in durations if d > ENGINE_PERIODIC_THRESHOLD_MS)
        for grace, durations in measured.items()
    }

    assert counts == {0: 63, 500: 8, 1000: 6, 1500: 4, 2000: 4}
    assert over_threshold == {0: 0, 500: 0, 1000: 1, 1500: 1, 2000: 1}
    assert max(measured[500]) == 2934
    assert measured[1500] == [0, 200, 33, 6500]

    # And the default the detector actually ships is the row that produces those four.
    assert Config().thresholds.ppe_grace_ms == 1500


def test_periodic_durations_are_milliseconds_not_truncated_seconds(
    differential: _Differential,
) -> None:
    """Bug #10: the original sent `int(elapsed_seconds)` next to a millisecond `startTime`.

    Applying that formula to the four windows the rewrite found turns 0/200/33/6500 into
    0/0/0/6 -- three of the four collapse to zero, and the surviving one loses 500 ms of
    what was observed. The truncation is toward zero and unsigned, so a violation shorter
    than a second was indistinguishable from no violation at all.
    """
    periods = [fields[2] for _index, fields in _new_of(differential.new, "NO_JACKET")]
    legacy_formula = [int(p / 1000) for p in periods if p is not None]

    assert periods == [0, 200, 33, 6500]
    assert legacy_formula == [0, 0, 0, 6]

    # And the countable events still carry no duration at all, so `/event/periodic-events`
    # cannot sum a gesture into a PPE total.
    for event in differential.new.events:
        if not event.event_type.is_periodic:
            assert event.time_period_ms is None


# --------------------------------------------------------------------------
# FALL -- a finding, not the expected difference
# --------------------------------------------------------------------------


def test_fall_count_is_unchanged_but_the_published_incident_moves(
    differential: _Differential,
) -> None:
    """**The expected difference did not happen.** FALL was expected to go from 1 to 2.

    Measured: one FALL either way. The trace holds 19 `fall` detections. The first, at
    15733 ms, is on a frame with **no detectable person** -- the only one of the 19 that is
    -- so `aiModule.py` line 310's `continue` skipped it and the original's first *reachable*
    fall was the one at 24066 ms. The rewrite has no early exit, so it publishes 15733; and
    `FallThrottle`, at the original's own 3-minute cooldown, then suppresses everything up
    to 195733 ms, which includes the 24066 fall 8333 ms later.

    So the rewrite reports the fall **8.3 seconds earlier** and reports the *first* incident
    rather than the second -- but with a 180000 ms cooldown on a 32833 ms clip, no
    configuration of this code publishes both. Whether 15733 and 24066 are one incident or
    two is a question the trace cannot answer and this test does not pretend to; what it
    pins is that the count did not change and the timestamp did.
    """
    falls = _detections(differential.records, "fall")
    assert len(falls) == 19

    first_index, first_ms, first_conf = falls[0]
    assert (first_index, first_ms) == (472, 15733)
    assert differential.records[first_index]["pose"]["keypoints_xy"] == [], (
        "frame 472 now has a person in it, so the reason the original missed the first "
        "fall no longer holds and this comparison needs rereading"
    )
    assert sum(
        1 for index, _ms, _conf in falls if not differential.records[index]["pose"]["keypoints_xy"]
    ) == 1

    legacy = _legacy_of(differential.legacy, "FALL")
    new = _new_of(differential.new, "FALL")
    assert len(legacy) == len(new) == 1

    (legacy_index, (legacy_start, legacy_conf, legacy_period)) = legacy[0]
    (new_index, (new_start, new_conf, new_period)) = new[0]

    assert (legacy_index, legacy_start) == (722, 24066)
    assert (new_index, new_start) == (472, 15733)
    assert legacy_start - new_start == 8333
    assert legacy_period is None and new_period is None

    # The confidence follows the incident: each run reports the detection confidence of the
    # box it published, and FALL is the one event the original already got this right on.
    assert new_conf == first_conf
    assert legacy_conf == next(conf for _i, ms, conf in falls if ms == 24066)


def test_the_throttle_collapses_every_other_fall_detection(
    differential: _Differential,
) -> None:
    """18 of the 19 detections are suppressed, and the cooldown outlives the whole clip.

    The original collapsed 17 of the 18 it could see. The count differs only because the
    rewrite starts the cooldown 8333 ms earlier.
    """
    falls = _detections(differential.records, "fall")
    published = _new_of(differential.new, "FALL")

    assert len(falls) - len(published) == 18

    cooldown_ms = Config().thresholds.fall_cooldown_ms
    assert cooldown_ms == 180_000
    clip_ms = differential.records[-1]["timestamp_ms"] - differential.records[0]["timestamp_ms"]
    assert clip_ms == 32_833
    assert cooldown_ms > clip_ms, (
        "the cooldown no longer outlives the clip, so more than one FALL can now be "
        "published and the finding in this module's docstring needs remeasuring"
    )


# --------------------------------------------------------------------------
# ARMS_UP and FRONT_BEND -- the second finding
# --------------------------------------------------------------------------


def test_gestures_are_zero_in_both_runs_because_the_footage_holds_none(
    differential: _Differential,
) -> None:
    """**The expected difference did not happen**, and the reason is the footage.

    Both runs emit zero ARMS_UP and zero FRONT_BEND. The original's reason is documented:
    a latch that armed once per slot and never re-armed. But the rewrite's latch *does*
    re-arm, and it still emits zero -- because measured over all 1114 person-frames the
    footage contains neither gesture:

    * ARMS_UP watches hip-shoulder-elbow, arms below 30 deg and completes above 140. The
      angle never exceeds **121.5 deg**. Nobody in this clip raises their arms.
    * FRONT_BEND watches shoulder-hip-knee, arms below 130 deg and completes above 160. The
      angle never falls below **156.4 deg**. Nobody in this clip bends.

    A visibility gate passing 964 and 811 times says a limb was seen, not that a gesture
    happened. This trace therefore cannot promote a single gesture assertion out of the
    synthetic tier, and `test_pose_rules.py` remains the only evidence for the re-arming
    latch.
    """
    assert _legacy_of(differential.legacy, "ARMS_UP") == []
    assert _legacy_of(differential.legacy, "FRONT_BEND") == []
    assert _new_of(differential.new, "ARMS_UP") == []
    assert _new_of(differential.new, "FRONT_BEND") == []

    config = Config()
    by_type = {spec.event_type: spec for spec in config.gestures}
    measured = _measured_gesture_angles(differential.records, config)

    arms_up = measured[EventType.ARMS_UP]
    assert len(arms_up) == 964
    assert max(arms_up) == pytest.approx(121.5, abs=0.1)
    assert max(arms_up) < by_type[EventType.ARMS_UP].relaxing, (
        "an arm raise now completes in this footage, so zero ARMS_UP is no longer explained "
        "by the input and the difference has to be re-derived"
    )

    front_bend = measured[EventType.FRONT_BEND]
    assert len(front_bend) == 330
    assert min(front_bend) == pytest.approx(156.4, abs=0.1)
    assert min(front_bend) > by_type[EventType.FRONT_BEND].maintaining, (
        "a bend now arms in this footage, so zero FRONT_BEND is no longer explained by the "
        "input"
    )


def test_no_gesture_was_decided_on_an_ungated_side(differential: _Differential) -> None:
    """The alarm check for gestures, asserted even though it is vacuous here.

    Zero gesture events means no frame can have emitted one without a side passing its
    visibility gate. Kept so that the day this trace does contain a gesture, the check is
    already in place rather than being written after the fact around whatever appeared.
    """
    gestures = [
        event
        for event in differential.new.events
        if event.event_type in (EventType.ARMS_UP, EventType.FRONT_BEND)
    ]
    assert gestures == []


# --------------------------------------------------------------------------
# Confidence provenance
# --------------------------------------------------------------------------


def test_every_published_confidence_is_a_detection_confidence(
    differential: _Differential,
) -> None:
    """Bugs #5/#7: `confidencePercentage` was a keypoint *visibility* score.

    Both populations are in the trace, so the swap is directly observable. On this footage
    the only published confidences are FALL's and NO_JACKET's, and both are PPE-model box
    confidences: FALL verbatim, NO_JACKET as the mean over its window's samples. None of
    them appears anywhere in the 18938 per-keypoint visibility scores.
    """
    keypoint_conf = {
        float(score)
        for record in differential.records
        for person in record["pose"]["keypoint_conf"]
        for score in person
    }
    object_conf = {
        float(detection["confidence"])
        for record in differential.records
        for detection in record["objects"]
    }
    assert len(keypoint_conf) == 18808 and len(object_conf) == 93
    assert not (object_conf & keypoint_conf)

    for event in differential.new.events:
        if event.event_type is EventType.FALL:
            assert event.confidence in object_conf
        else:
            assert min(object_conf) <= event.confidence <= max(object_conf)
        assert event.confidence not in keypoint_conf


def test_the_gesture_rule_was_handed_box_confidence_not_keypoint_visibility(
    differential: _Differential,
) -> None:
    """What a gesture *would* have published, shown where it can still be shown.

    Neither run emits a gesture on this footage, so the swap cannot be read off the
    published events. It can be read off the value that reached the rule: the pipeline hands
    `GestureDetector` the person-box confidence, and `pose_rules` publishes that field
    verbatim. The spy records all 1114 of them, in model order, and they are exactly the
    trace's `box_conf` column -- while the two indices the original published, `row[7]` (left
    elbow visibility, ARMS_UP) and `row[11]` (left hip visibility, FRONT_BEND), differ from
    the box confidence on every single person-frame.
    """
    expected = [
        float(conf) for record in differential.records for conf in record["pose"]["box_conf"]
    ]
    handed = [observation.detection_confidence for observation in differential.new.observations]

    assert len(handed) == 1114
    assert handed == expected

    legacy_arms_up = [
        float(person[7]) for record in differential.records
        for person in record["pose"]["keypoint_conf"]
    ]
    legacy_front_bend = [
        float(person[11]) for record in differential.records
        for person in record["pose"]["keypoint_conf"]
    ]
    assert sum(1 for a, b in zip(legacy_arms_up, expected, strict=True) if a == b) == 0
    assert sum(1 for a, b in zip(legacy_front_bend, expected, strict=True) if a == b) == 0


# --------------------------------------------------------------------------
# NO_HELMET -- a gap, stated as one
# --------------------------------------------------------------------------


def test_no_helmet_is_untested_by_this_trace(differential: _Differential) -> None:
    """Zero in both runs, and zero evidence either way.

    The clip contains no `no-helmet` detection at all, so the two runs agreeing on zero says
    nothing about the helmet path. Asserted so that a future trace containing one fails here
    and forces the comparison to be extended rather than silently inheriting a green tick.
    """
    assert _detections(differential.records, "no-helmet") == []
    assert _legacy_of(differential.legacy, "NO_HELMET") == []
    assert _new_of(differential.new, "NO_HELMET") == []


# --------------------------------------------------------------------------
# Nothing appeared that neither run can account for
# --------------------------------------------------------------------------


def test_no_event_came_from_a_frame_that_never_detected_it(
    differential: _Differential,
) -> None:
    """The alarm check: every published event traces back to a detection in the trace.

    A FALL at a timestamp carrying no `fall` box, or a NO_JACKET window starting on a frame
    carrying no `no-jacket` box, would mean the rules invented an incident -- which is the
    one outcome this differential exists to rule out.
    """
    frame_times = {record["timestamp_ms"] for record in differential.records}
    fall_times = {ms for _i, ms, _c in _detections(differential.records, "fall")}
    jacket_times = {ms for _i, ms, _c in _detections(differential.records, "no-jacket")}

    for event in differential.new.events:
        assert event.start_time_ms in frame_times, (
            f"{event.event_type.value} at {event.start_time_ms} ms is not any frame's time"
        )
        assert event.camera_name == CAMERA
        if event.event_type is EventType.FALL:
            assert event.start_time_ms in fall_times
        elif event.event_type is EventType.NO_JACKET:
            assert event.start_time_ms in jacket_times

    for index, event in zip(
        differential.legacy.frame_indices, differential.legacy.events, strict=True
    ):
        assert differential.records[index]["timestamp_ms"] in frame_times
        if event["eventType"] == "FALL":
            assert differential.records[index]["timestamp_ms"] in fall_times


def test_differential_is_fast_enough_to_keep(differential: _Differential) -> None:
    """986 frames through both implementations, in well under a second.

    The whole point of the rewrite's seams is that the suite runs without a camera, a GPU or
    a broker; a differential that reintroduced a slow inner loop would be paid for on every
    commit. The bound is loose because it is a smoke alarm, not a benchmark -- measured at
    about 20 ms to parse the trace, 3 ms for the legacy replay and 11 ms for the pipeline --
    a 40 ms module fixture, and 0.09 s for this file end to end.
    """
    assert differential.new.seconds < 5.0
    assert differential.legacy.seconds < 5.0
    assert differential.total_seconds < 15.0


# --------------------------------------------------------------------------
# Support for the gesture finding
# --------------------------------------------------------------------------


def _measured_gesture_angles(
    records: Sequence[dict], config: Config
) -> dict[EventType, list[float]]:
    """Every angle the rewrite's gesture rules actually decided on, per gesture.

    This is `GestureDetector._read_sides` and its mean, recomputed here over the whole trace
    so the *reason* both gestures stay at zero can be asserted as a number rather than
    asserted as an absence. It reads the same `Config`, the same gates, the same chains and
    the same `joint_angle`; what it does not reproduce is the hysteresis, which is the part
    under test.
    """
    threshold = config.thresholds.keypoint_visibility
    measured: dict[EventType, list[float]] = {spec.event_type: [] for spec in config.gestures}

    for record in records:
        pose = record["pose"]
        for keypoints, confidences in zip(
            pose["keypoints_xy"], pose["keypoint_conf"], strict=True
        ):
            for spec in config.gestures:
                sides: list[tuple[float, float | None]] = []
                for side in ("left", "right"):
                    gate = getattr(spec, f"{side}_visibility_idx")
                    if not all(confidences[index] > threshold for index in gate):
                        continue
                    chain = getattr(spec, f"{side}_points_idx")
                    upright = getattr(config.upright, f"{side}_idx")
                    try:
                        angle = joint_angle([tuple(keypoints[i]) for i in chain])
                        posture = (
                            joint_angle([tuple(keypoints[i]) for i in upright])
                            if spec.requires_upright
                            else None
                        )
                    except ValueError:
                        continue
                    sides.append((angle, posture))

                if not sides:
                    continue
                if spec.requires_upright:
                    postures = [posture for _angle, posture in sides if posture is not None]
                    if not sum(postures) / len(postures) > config.upright.angle_degrees:
                        continue
                measured[spec.event_type].append(sum(a for a, _p in sides) / len(sides))

    return measured
