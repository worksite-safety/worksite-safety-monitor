"""Unit tests for `worksite_detector.ppe_rules` -- PPE violation windows and FALL throttling.

This module replaces `aiModule.py` lines 408-512, which carry six confirmed defects.
Every test below names the one it pins:

1. **`NO_JACKET` is never published.** `controlJacket` is set `False` at line 409 and
   again at 428 -- the second assignment is a no-op where `True` was plainly meant --
   so the emit condition at 489 can never hold. On 986 frames of real footage carrying
   63 frames of `no-jacket` detections, the original emits **zero** events.
2. **`checkLastSendJacket` never clears.** Line 512 is unreachable, so the flag latches
   `True` for the life of the process after the first detection.
3. **`sumHelmet`/`numHelmet`/`sumJacket`/`numJacket` are never reset**, so the reported
   confidence is a session-long running mean, not a per-violation one.
4. **`timePeriod` is `int(seconds)` beside a millisecond `startTime`**, and `int()`
   truncates toward zero, so a 2.99 s violation reports `2` against the engine's `> 3`.
5. **The window never closes when nobody is in frame.** The `continue` at line 310 skips
   the whole block, so a violation that ends by the worker walking out of shot stays open
   and later emits an absurd duration.
6. **Helmet and jacket run on separate, asymmetric ad-hoc flags** rather than one
   mechanism, which is how (1) and (2) could exist on one side and not the other.

**Why a grace window exists at all.** `tests/data/baseline/PROVENANCE.md` measures the
real clip: the `no-jacket` detections are fragmented into 27 runs across 63 frames, the
longest 367 ms. Against the engine's 3-second periodic threshold, *zero* of those runs
survive. Merging them with `grace_ms=1500` turns the same footage into one coherent
6500 ms violation. The grace period is not a refinement -- without it, fixing defect (1)
still records nothing.

**Why `violations` is a Mapping to confidence rather than a set.** The original published
`row[7]`/`row[11]` -- a keypoint *visibility* score -- as `confidencePercentage`. Carrying
the detection confidence per violation is what lets the emitted event report the real
number, and the mean has to be scoped to the window that produced it (defect 3).

**Deliberately left unpinned:** two `observe` calls carrying the same `frame_time_ms`
double-count a confidence sample and so bias that window's mean slightly. The pipeline
calls `observe` exactly once per frame, so a duplicate is a caller bug -- but raising in a
real-time loop over a marginally skewed mean is the worse outcome of the two. This was
considered and left open on purpose; it is not an oversight, and it must not be guarded.
"""
from __future__ import annotations

from typing import Any

import pytest
from worksite_detector.events import DetectionEvent, EventType
from worksite_detector.ppe_rules import FallThrottle, PpeViolationTracker

HELMET = EventType.NO_HELMET
JACKET = EventType.NO_JACKET

CAMERA = "kamera-üst"

# Any confidence that is not itself under test. Kept off 1.0 so a stray default cannot
# masquerade as a real reading.
CONF = 0.9

# Confidences are means of floats; 1e-9 is far wider than double-precision error and far
# tighter than anything that would change a displayed percentage.
TOL = 1e-9

# The documented default. Every test that does not pass `grace_ms` is asserting against it.
DEFAULT_GRACE_MS = 1500

# timedelta(minutes=3), aiModule.py line 437.
COOLDOWN_MS = 180_000

# `event.fall.threshold.value` in the engine's application.yml. RawEventService.listener
# persists a periodic event only if its duration is STRICTLY over this, so anything the
# tracker under-reports is dropped downstream in silence.
ENGINE_PERIODIC_THRESHOLD_MS = 3000

Frames = list[tuple[int, dict[EventType, float]]]


def _tracker(**kwargs: Any) -> PpeViolationTracker:
    return PpeViolationTracker(camera_name=CAMERA, **kwargs)


def _feed(tracker: PpeViolationTracker, frames: Frames) -> list[DetectionEvent]:
    """Run every frame through `observe` and return the events in emission order."""
    emitted: list[DetectionEvent] = []
    for frame_time_ms, violations in frames:
        emitted.extend(tracker.observe(frame_time_ms, violations))
    return emitted


def _only(events: list[DetectionEvent]) -> DetectionEvent:
    """The single event, or a failure that shows what actually came out."""
    assert len(events) == 1, (
        f"expected exactly one event, got {len(events)}: "
        f"{[(e.event_type, e.start_time_ms, e.time_period_ms) for e in events]}"
    )
    return events[0]


def _closing_sequence(event_type: EventType) -> Frames:
    """Two violating frames 100 ms apart, then two clean ones; the second clean frame
    sits 1600 ms past the last violation and so must close the window."""
    return [
        (0, {event_type: CONF}),
        (100, {event_type: CONF}),
        (200, {}),
        (1700, {}),
    ]


# --------------------------------------------------------------------------
# Window lifecycle
# --------------------------------------------------------------------------


def test_first_violation_frame_emits_nothing() -> None:
    # A window opens; nothing is known about its duration yet. Emitting here would
    # reproduce defect 4's zero-length events from the other direction.
    assert _tracker().observe(0, {HELMET: CONF}) == []


def test_ongoing_violation_emits_nothing() -> None:
    # Three consecutive violating frames are one violation, not three. The legacy flags
    # made this accidental rather than designed (defect 6).
    tracker = _tracker()

    emitted = _feed(tracker, [(0, {HELMET: CONF}), (33, {HELMET: CONF}), (66, {HELMET: CONF})])

    assert emitted == []


def test_window_closes_after_grace() -> None:
    # Pins defect 5 / the grace contract: the close must happen on the frame where the
    # grace has elapsed (1700), not on the first clean frame (200) as the legacy did.
    tracker = _tracker()

    per_frame = [len(tracker.observe(t, v)) for t, v in _closing_sequence(HELMET)]

    assert per_frame == [0, 0, 0, 1]


def test_time_period_excludes_grace() -> None:
    # The grace is a merge tolerance, not part of the violation. Counting it would report
    # 1600 (or 1700) ms for a 100 ms violation and push sub-threshold noise over the
    # engine's `> 3 s` gate.
    event = _only(_feed(_tracker(), _closing_sequence(HELMET)))

    assert event.time_period_ms == 100


def test_start_time_is_window_open_time() -> None:
    # `startTime` is when the violation began, not when the tracker noticed it ended;
    # the dashboard buckets events by this field, so a close-time value lands the event
    # in the wrong day bucket near midnight.
    event = _only(_feed(_tracker(), _closing_sequence(HELMET)))

    assert event.start_time_ms == 0


def test_closes_at_exactly_grace_boundary() -> None:
    # The boundary is `>=`: exactly `grace_ms` of silence closes the window. Pinned
    # against its 1-ms-early twin below so an off-by-one cannot pass both. Asserted
    # per frame, not as a total, so a tracker that closes early cannot pass by accident.
    tracker = _tracker()
    frames: Frames = [(0, {HELMET: CONF}), (200, {HELMET: CONF}), (1700, {})]

    per_frame = [len(tracker.observe(t, v)) for t, v in frames]

    assert per_frame == [0, 0, 1]


def test_does_not_close_one_ms_early() -> None:
    # 1499 ms of silence is still inside the grace. Closing here would re-fragment the
    # real footage's 27 `no-jacket` runs that the 1500 ms window exists to merge.
    tracker = _tracker()

    emitted = _feed(tracker, [(0, {HELMET: CONF}), (200, {HELMET: CONF}), (1699, {})])

    assert emitted == []


def test_violation_returning_inside_grace_extends_window() -> None:
    # THE measurement-driven behaviour: PROVENANCE.md shows 63 fragmented `no-jacket`
    # frames collapsing to one 6500 ms violation only because a return inside the grace
    # extends the open window instead of opening a second one.
    tracker = _tracker()

    emitted = _feed(
        tracker,
        [(0, {HELMET: CONF}), (500, {}), (1000, {HELMET: CONF}), (3000, {})],
    )
    event = _only(emitted)

    assert (event.start_time_ms, event.time_period_ms) == (0, 1000)


def test_fragmented_runs_merge_into_one_recordable_violation() -> None:
    # The empirical result from PROVENANCE.md, in miniature: the real clip's `no-jacket`
    # detections arrive as 27 runs, the longest 367 ms, and NOT ONE clears the engine's
    # 3 s threshold on its own. Merging across sub-grace gaps is the only reason the
    # footage records anything at all. Eight fragments over 6500 ms, every gap under the
    # 1500 ms grace, must arrive as one event that clears the threshold.
    tracker = _tracker()
    fragments = [0, 100, 1200, 1300, 2500, 3600, 4700, 5900, 6500]

    emitted = _feed(
        tracker,
        [(t, {JACKET: CONF}) for t in fragments] + [(8100, {})],
    )
    event = _only(emitted)

    assert event.time_period_ms == 6500, (
        f"got {event.time_period_ms} ms. The longest single fragment here is 1200 ms and "
        f"the engine drops anything not over {ENGINE_PERIODIC_THRESHOLD_MS} ms, so a "
        f"tracker that does not merge across the grace records nothing on real footage."
    )


def test_violation_after_grace_opens_new_window() -> None:
    # The mirror of the test above: once the grace has lapsed the window is finished, and
    # a later violation is a distinct event rather than one absurd merged duration.
    tracker = _tracker()

    emitted = _feed(
        tracker,
        [
            (0, {HELMET: CONF}),
            (500, {HELMET: CONF}),
            (2500, {}),  # closes window A
            (3000, {HELMET: CONF}),
            (3500, {HELMET: CONF}),
            (6000, {}),  # closes window B
        ],
    )

    assert [e.start_time_ms for e in emitted] == [0, 3000]


def test_violation_after_grace_with_no_clean_frame_closes_and_reopens() -> None:
    # Silence is not evidence of continuation. `observe` runs once per frame, so a 5000 ms
    # gap between violating frames means the tracker was told nothing for five seconds and
    # cannot claim the violation persisted through them -- inventing an unobserved duration
    # is exactly the defect class here (the legacy window stayed open across unobserved
    # stretches and later emitted absurd periods). Two windows, both of measured length 0.
    tracker = _tracker()
    frames: Frames = [(0, {HELMET: CONF}), (5000, {HELMET: CONF}), (7000, {})]

    per_frame = [
        [(e.start_time_ms, e.time_period_ms) for e in tracker.observe(t, v)] for t, v in frames
    ]

    assert per_frame == [[], [(0, 0)], [(5000, 0)]]


# --------------------------------------------------------------------------
# Confidence
# --------------------------------------------------------------------------


def test_mean_confidence_is_window_scoped() -> None:
    # Pins defect 3: `sumHelmet`/`numHelmet` are never reset (aiModule.py 419-420), so the
    # legacy would report (0.9+0.9+0.1+0.1)/4 = 0.5 for the second window.
    tracker = _tracker()

    _feed(tracker, [(0, {HELMET: 0.9}), (100, {HELMET: 0.9}), (2000, {})])
    second = _feed(tracker, [(3000, {HELMET: 0.1}), (3100, {HELMET: 0.1}), (5000, {})])

    assert _only(second).confidence == pytest.approx(0.1, abs=TOL)


def test_mean_confidence_averages_within_window() -> None:
    # The reported figure is the mean over the window's samples, so a violation seen
    # weakly then strongly reports neither extreme.
    emitted = _feed(_tracker(), [(0, {HELMET: 0.6}), (100, {HELMET: 1.0}), (2000, {})])

    assert _only(emitted).confidence == pytest.approx(0.8, abs=TOL)


def test_confidence_taken_from_the_mapping_value() -> None:
    # Pins defect: the original published `row[11]`, a keypoint *visibility* score
    # (aiModule.py 343), as `confidencePercentage`. 0.63 goes in, 0.63 must come out.
    emitted = _feed(_tracker(), [(0, {HELMET: 0.63}), (2000, {})])

    assert _only(emitted).confidence == pytest.approx(0.63, abs=TOL)


# --------------------------------------------------------------------------
# Symmetry -- the headline bug
# --------------------------------------------------------------------------


def test_no_jacket_behaves_identically_to_no_helmet() -> None:
    # THE HEADLINE REGRESSION (defect 1): `controlJacket = False` at aiModule.py 428 makes
    # the emit at 489 unreachable, so 63 frames of real `no-jacket` footage produced zero
    # events. Identical input on the jacket path must now produce the identical event.
    emitted = _feed(_tracker(), _closing_sequence(JACKET))
    event = _only(emitted)

    assert (event.event_type, event.start_time_ms, event.time_period_ms) == (JACKET, 0, 100)


def test_windows_are_independent_per_type() -> None:
    # Pins defect 6: one mechanism, one window per tracked type. Overlapping helmet and
    # jacket violations must not share `last_insert_time` or close each other early.
    tracker = _tracker()

    emitted = _feed(
        tracker,
        [
            (0, {HELMET: CONF}),
            (500, {HELMET: CONF, JACKET: CONF}),
            (1000, {HELMET: CONF, JACKET: CONF}),
            (2000, {JACKET: CONF}),
            (4000, {}),
        ],
    )

    assert {e.event_type: (e.start_time_ms, e.time_period_ms) for e in emitted} == {
        HELMET: (0, 1000),
        JACKET: (500, 1500),
    }


def test_one_event_regardless_of_violator_count() -> None:
    # DOCUMENTS AN AGREED LIMITATION, not a defect: `violations` has one entry per event
    # type, so three bare-headed workers in frame are one NO_HELMET window, not three.
    # Per-person attribution would need a tracker id the pose stage does not produce.
    tracker = _tracker()

    emitted = _feed(
        tracker,
        [
            (0, {HELMET: 0.9}),  # three people, all bare-headed, collapsed to one key
            (100, {HELMET: 0.8}),
            (200, {HELMET: 0.7}),
            (2000, {}),
        ],
    )

    assert len(emitted) == 1


# --------------------------------------------------------------------------
# Person-free frames
# --------------------------------------------------------------------------


def test_empty_violations_closes_an_open_window() -> None:
    # Pins defect 5: the `continue` at aiModule.py 310 skipped the emit block whenever no
    # person was detected, so a violation ending by the worker leaving frame stayed open
    # forever. PROVENANCE.md counts 278 person-free frames in 31 blocks on the real clip.
    tracker = _tracker()

    emitted = _feed(tracker, [(0, {HELMET: CONF}), (1000, {HELMET: CONF}), (3000, {})])

    assert _only(emitted).time_period_ms == 1000


def test_empty_violations_on_fresh_tracker_is_noop() -> None:
    # `observe` is called on EVERY frame, and most frames are clean. A hundred of them
    # must neither emit nor leave a half-open window behind for `flush` to find.
    tracker = _tracker()

    emitted = _feed(tracker, [(t, {}) for t in range(0, 10_000, 100)])

    assert emitted + tracker.flush(10_000) == []


# --------------------------------------------------------------------------
# flush
# --------------------------------------------------------------------------


def test_flush_emits_open_window() -> None:
    # Shutdown must not swallow a violation that is still in progress; the legacy simply
    # lost it, because nothing ran after the frame loop.
    tracker = _tracker()
    _feed(tracker, [(0, {HELMET: CONF}), (1000, {HELMET: CONF})])

    assert _only(tracker.flush(1000)).time_period_ms == 1000


def test_flush_uses_last_seen_not_now() -> None:
    # A slow shutdown -- model teardown, Kafka drain -- must not inflate the duration.
    # Measuring to `now_ms` is how the legacy produced its absurd multi-hour periods.
    tracker = _tracker()
    _feed(tracker, [(0, {HELMET: CONF}), (1000, {HELMET: CONF})])

    event = _only(tracker.flush(9999))

    assert (event.start_time_ms, event.time_period_ms) == (0, 1000)


def test_flush_is_idempotent() -> None:
    # Pins defect 2 in its new form: a latched flag would re-emit the same window on every
    # call. Shutdown paths get invoked twice (signal handler plus `finally`) routinely.
    tracker = _tracker()
    _feed(tracker, [(0, {HELMET: CONF}), (1000, {HELMET: CONF})])
    tracker.flush(1000)

    assert tracker.flush(2000) == []


def test_flush_with_nothing_open_returns_empty() -> None:
    # The common case: the clip ends on clean frames. Nothing open means nothing sent.
    assert _tracker().flush(5000) == []


def test_flush_emits_all_open_windows_in_tracked_order() -> None:
    # Order is `tracked` order, not the order the windows happened to open -- otherwise the
    # shutdown batch is dict-insertion-ordered and the baseline diff is unstable noise.
    # Jacket opens first here precisely so insertion order would give the wrong answer.
    tracker = _tracker()
    _feed(tracker, [(0, {JACKET: CONF}), (100, {HELMET: CONF, JACKET: CONF})])

    emitted = tracker.flush(200)

    assert [e.event_type for e in emitted] == [HELMET, JACKET]


# --------------------------------------------------------------------------
# Degenerate input
# --------------------------------------------------------------------------


def test_single_frame_window_has_zero_period() -> None:
    # DOCUMENTS A DELIBERATE NON-BEHAVIOUR: a one-frame violation reports 0 ms and is still
    # emitted. Dropping short violations is `RawEventService`'s job via
    # `event.fall.threshold.value`; a second, silent filter here would be undiagnosable.
    emitted = _feed(_tracker(), [(0, {HELMET: CONF}), (2000, {})])

    assert _only(emitted).time_period_ms == 0


def test_non_monotonic_time_never_yields_negative_period() -> None:
    # Camera clock skew and frame reordering both go backwards. A negative `timePeriod`
    # raises out of `DetectionEvent`, killing the listener thread, or -- if it got through
    # -- fails the engine's `> threshold` test and vanishes without a trace.
    emitted = _feed(_tracker(), [(1000, {HELMET: CONF}), (900, {HELMET: CONF}), (5000, {})])

    assert _only(emitted).time_period_ms == 0


@pytest.mark.parametrize(
    "event_type",
    [EventType.FALL, EventType.ARMS_UP, EventType.FRONT_BEND],
    ids=lambda member: member.name,
)
def test_untracked_event_type_raises(event_type: EventType) -> None:
    # Countable events have no window; routing one here means the pipeline is mis-wired.
    # Silently ignoring it is how the legacy lost NO_JACKET for the project's whole life.
    with pytest.raises(ValueError):
        _tracker().observe(0, {event_type: CONF})


def test_narrowed_tracked_rejects_an_untracked_periodic_type() -> None:
    # The rule is "anything outside `tracked` is a wiring error", and it must not soften
    # just because the intruder is a periodic type this instance happens not to watch.
    # Dropping it silently is bug #1 in a new costume: detected, then never reported.
    tracker = PpeViolationTracker(camera_name=CAMERA, tracked=(HELMET,))

    with pytest.raises(ValueError):
        tracker.observe(0, {JACKET: CONF})


@pytest.mark.parametrize("confidence", [-0.1, -0.0001, 1.0001, 1.5, 100.0])
def test_confidence_outside_unit_interval_raises(confidence: float) -> None:
    # Must raise on the offending frame, not later at emit time: a bad sample averaged
    # against good ones lands back inside [0, 1] and reaches the dashboard as a plausible
    # wrong percentage. `confidencePercentage` is a fraction here; the web layer x100s it.
    with pytest.raises(ValueError):
        _tracker().observe(0, {HELMET: confidence})


# --------------------------------------------------------------------------
# Constructor wiring
#
# NOT ON THE ORIGINAL TEST LIST -- added because without them an implementation that
# hardcodes the camera name or ignores `grace_ms` passes every other test in this file.
# --------------------------------------------------------------------------


def test_event_carries_configured_camera_name() -> None:
    # `cameraName` is how the dashboard attributes a violation to a site. The legacy sent
    # `args.input`, a video path, and it is the only free-text field the engine stores.
    emitted = _feed(_tracker(), [(0, {HELMET: CONF}), (2000, {})])

    assert _only(emitted).camera_name == CAMERA


def test_custom_grace_ms_is_honoured() -> None:
    # PROVENANCE.md's table (0/500/1000/1500/2000 ms) was produced by sweeping this
    # parameter, so it has to be a real input rather than a decorative default. Both
    # sides of the custom boundary are pinned: 400 ms of silence is too soon, 600 is not.
    tracker = _tracker(grace_ms=500)
    frames: Frames = [(0, {HELMET: CONF}), (400, {}), (600, {})]

    per_frame = [len(tracker.observe(t, v)) for t, v in frames]

    assert per_frame == [0, 0, 1], (
        f"got {per_frame} with grace_ms=500. [0, 0, 0] means the {DEFAULT_GRACE_MS} ms "
        f"default is hardcoded; [0, 1, 0] means the grace is ignored entirely."
    )


@pytest.mark.parametrize("grace_ms", [-1, -1500])
def test_negative_grace_ms_raises(grace_ms: int) -> None:
    # A negative grace inverts the `now - last >= grace` close condition into something
    # incoherent -- every window closes on the frame after it opens -- rather than failing.
    # Refuse it at construction, where the stack trace still points at the caller.
    with pytest.raises(ValueError):
        _tracker(grace_ms=grace_ms)


# --------------------------------------------------------------------------
# FallThrottle
# --------------------------------------------------------------------------


def test_first_fall_always_allowed() -> None:
    # The legacy faked this by initialising `reference_time` to three minutes in the past
    # (aiModule.py's `datetime.now() - timedelta(minutes=3)`); a naive rewrite that starts
    # the reference at 0 denies the very first fall of the session under `now > reference`.
    assert FallThrottle(cooldown_ms=COOLDOWN_MS).allow(0) is True


def test_second_fall_within_cooldown_denied() -> None:
    # One person falling is one event. PROVENANCE.md counts 19 `fall` detections over 10 s
    # on the real clip, and each one mails EVERY user in the database.
    throttle = FallThrottle(cooldown_ms=COOLDOWN_MS)

    assert [throttle.allow(0), throttle.allow(179_999)] == [True, False]


def test_boundary_is_strictly_greater_than() -> None:
    # Matches the original's `current_datetime > reference_time` (aiModule.py 436) exactly:
    # the cooldown instant itself is still denied, the millisecond after it is allowed.
    throttle = FallThrottle(cooldown_ms=COOLDOWN_MS)
    throttle.allow(0)

    assert [throttle.allow(180_000), throttle.allow(180_001)] == [False, True]


def test_denied_attempt_does_not_extend_cooldown() -> None:
    # The original advances `reference_time` only inside the allowed branch (line 437). A
    # rewrite that updates unconditionally turns 19 consecutive detections into a rolling
    # block that suppresses the *next* real fall too.
    throttle = FallThrottle(cooldown_ms=COOLDOWN_MS)

    assert [throttle.allow(0), throttle.allow(100_000), throttle.allow(180_001)] == [
        True,
        False,
        True,
    ]


def test_zero_cooldown_allows_everything() -> None:
    # READ THIS WITH test_first_fall_always_allowed -- together the two forbid the obvious
    # millisecond port of aiModule.py line 279. Initialising `reference = -cooldown_ms`
    # (the literal analogue of `datetime.now() - timedelta(minutes=3)`) satisfies the first
    # fall at cooldown 180_000, but at cooldown 0 the reference starts at 0 and `0 > 0`
    # denies the very first call. A "never fired" sentinel is required, not an offset.
    #
    # Disabling the throttle must also be expressible without a special case. Timestamps
    # advance because the contract is strictly-greater-than; this pins "no cooldown", not
    # "two calls in the same millisecond", which stays deliberately unspecified.
    throttle = FallThrottle(cooldown_ms=0)

    assert [throttle.allow(0), throttle.allow(1), throttle.allow(2)] == [True, True, True]


@pytest.mark.parametrize("cooldown_ms", [-1, -180_000])
def test_negative_cooldown_ms_raises(cooldown_ms: int) -> None:
    # A negative cooldown re-arms the throttle in the past, so it never throttles anything
    # and all 19 `fall` detections on the real clip mail every user in the database.
    with pytest.raises(ValueError):
        FallThrottle(cooldown_ms=cooldown_ms)


def test_throttles_are_independent_per_instance() -> None:
    # The legacy's `reference_time` was a module-level loop variable, so a second camera in
    # the same process would have shared it and swallowed the other camera's falls.
    first = FallThrottle(cooldown_ms=COOLDOWN_MS)
    second = FallThrottle(cooldown_ms=COOLDOWN_MS)
    first.allow(0)

    assert [first.allow(1000), second.allow(1000)] == [False, True]
