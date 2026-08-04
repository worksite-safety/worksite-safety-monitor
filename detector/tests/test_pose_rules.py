"""Unit tests for `worksite_detector.pose_rules` -- gesture events from pose keypoints.

This module replaces `aiModule.py` lines 312-398, the densest defect cluster in the
original. Seven confirmed defects live in those 86 lines, and every test below names the
one it pins:

1. **The visibility gates are `or`, the angle is averaged unconditionally.** Lines 321 and
   358 admit a person on `left AND` *or* `right AND`, and `calculate_angle` (line 87) then
   averages both sides whatever the gate decided. A worker standing side-on has the unseen
   side's `(0, 0)` sentinels folded in -- `atan2(0, 0)` is `0.0`, not an error -- which
   roughly halves every angle before it reaches a threshold. `geometry.joint_angle` now
   refuses that input outright, so the fix has to be here: average only the sides that
   passed their own gate.
2. **The upright gate measures a chain nobody checked.** Line 321 gates
   shoulder-hip-knee; line 322 then measures hip-knee-**ankle**. Ankle confidence, indices
   15 and 16, is not read anywhere in the file, so the precondition that stops a seated
   worker being counted as bending was itself decided by two `(0, 0)` sentinels.
3. **`numberOfPerson = len(checkNodeVisibility[0])` counts keypoints, not people** (line
   315). It is 17 for any crowd, and `personIndex` wraps against it (line 397).
4. **The state arrays are `[0] * 10`.** The eleventh person in frame is an IndexError that
   takes the frame loop with it.
5. **State slots have no owner.** `angle`/`reaching`/`state_keep[personIndex]` are indexed
   by YOLO's detection order with no tracker at all, so slot 0's hysteresis history
   routinely belongs to a different human on the next frame. This is worse than defect 4:
   it is not bounded by crowd size and it needs only two people to happen.
6. **The latch can never re-arm.** Both gestures emit on the release edge only, and once a
   slot latches `reaching=True` while the relax threshold is never reached, that slot is
   silent for the life of the process. Replayed over 986 frames of real footage the
   original emitted **zero** ARMS_UP and **zero** FRONT_BEND -- not for want of input: the
   visibility gates passed 811 and 964 times.
7. **The published confidence is a keypoint visibility score.** `row[11]` and `row[7]`
   (lines 343 and 382) were sent as `confidencePercentage`, which the dashboard multiplies
   by 100 and shows to a safety officer as the detector's confidence in the event. Worse,
   when the `or` at line 321 or 358 passed through its right-hand branch those two indices
   were constrained by nothing, so the number published could be the near-zero score of a
   limb that was never seen.

**Every figure comes from `make_person`.** It builds a stick figure whose hip, shoulder and
knee chains measure exactly the angles asked for, and `tests/test_support.py` measures all
three back out through the same `joint_angle` the rules call. Hand-placed coordinates would
make each test an assertion about arithmetic nobody checked.

`make_person` returns `tests._support.builders.PersonObservation`, a structural stand-in
for the real value object, and the detector is fed it directly. That is deliberate: the
frozen field names and types are the contract, so `update` must read its argument by
attribute and must not `isinstance`-check it.

**Deliberately left unpinned:** two `update` calls carrying the same `frame_time_ms`, and a
frame whose timestamp runs backwards. Camera clock skew and frame reordering produce both,
and neither is guarded: `update` stamps an event with whatever frame time it was handed and
takes no state decision from the clock, so a reordered frame yields a mis-stamped event
rather than an exception inside a real-time loop. This was considered and left open on
purpose -- the same call `ppe_rules` makes about a duplicated frame -- and it must not be
"fixed" with a raise.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

import pytest

from tests._support.builders import (
    MISSING_POINT,
    PersonObservation as FixtureObservation,
    frame_sequence,
    make_person,
)
from tests._support.keypoints import (
    KEYPOINT_COUNT,
    LEFT_ANKLE,
    LEFT_ELBOW,
    LEFT_HIP,
    LEFT_SHOULDER,
    RIGHT_ANKLE,
    RIGHT_ELBOW,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    RIGHT_SIDE_INDICES,
)
from worksite_detector.config import Config
from worksite_detector.events import DetectionEvent, EventType
from worksite_detector.pose_rules import GestureDetector, PersonObservation

CAMERA = "kamera-üst"

# --------------------------------------------------------------------------
# Poses, in degrees. FRONT_BEND's hysteresis band is maintaining=130 / relaxing=160 and
# ARMS_UP's is 30 / 140 (`config._DEFAULT_GESTURES`, pinned by test_config.py); every
# constant here is chosen relative to those two bands and to the `> 160` upright gate.
# --------------------------------------------------------------------------

#: shoulder-hip-knee, over `relaxing`: releases the bend.
TORSO_STRAIGHT = 170.0
#: Under `maintaining`: arms the bend.
TORSO_BENT = 120.0
DEEPER_BEND = 110.0
SHALLOWER_BEND = 125.0
#: Strictly inside the band: holds whatever state it found.
TORSO_IN_BAND = 145.0
#: The bend a side-on worker is caught in; halving it (defect 1) reads 50.
SIDE_ON_BEND = 100.0

#: hip-shoulder-elbow. The band reads inverted -- the gesture called ARMS_UP arms at a
#: *small* angle -- because these are the original's numbers, kept as they were.
ARMS_GESTURE = 20.0
ARMS_NEUTRAL = 170.0

#: hip-knee-ankle, the posture precondition. The gate is `> 160`.
KNEE_STANDING = 175.0
KNEE_SEATED = 90.0
#: Between a 100-degree gate and the 160-degree default, for the constructor-wiring tests.
KNEE_CROUCHED = 120.0

#: Two person-box confidences, far enough apart to say which person an event came from.
BENDER_CONF = 0.91
BYSTANDER_CONF = 0.42

#: A stricter keypoint gate than the 0.6 default, and a figure either side of it. 0.7 clears
#: the default and not this one, which is what makes the argument's effect observable.
STRICT_VISIBILITY = 0.8
UNDER_STRICT_GATE = 0.7
OVER_STRICT_GATE = 0.85

#: A looser posture gate than the 160-degree default, paired with `KNEE_CROUCHED` above it
#: and `KNEE_SEATED` below it.
LOW_UPRIGHT_GATE = 100.0


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _detector(**kwargs: Any) -> GestureDetector:
    """A detector on the frozen default gestures unless a test says otherwise."""
    kwargs.setdefault("gestures", Config().gestures)
    kwargs.setdefault("camera_name", CAMERA)
    return GestureDetector(**kwargs)


def _bending(
    hip_deg: float,
    *,
    person_id: int = 0,
    knee_deg: float = KNEE_STANDING,
    shoulder_deg: float = ARMS_NEUTRAL,
    **kwargs: Any,
) -> FixtureObservation:
    """A figure posed for the FRONT_BEND chain, with the arms parked outside ARMS_UP's band.

    The arms default to `ARMS_NEUTRAL` so a whole `update` return value can be asserted: an
    arm angle inside ARMS_UP's band would add events that have nothing to do with the bend
    under test. `shoulder_deg` is overridable only for the constructor-wiring test, which
    points the posture chain at the arm; it is held constant across a sequence there, so
    ARMS_UP still never completes a cycle.
    """
    return make_person(
        person_id=person_id,
        hip_angle_deg=hip_deg,
        shoulder_angle_deg=shoulder_deg,
        knee_angle_deg=knee_deg,
        **kwargs,
    )


def _arms(
    shoulder_deg: float,
    *,
    person_id: int = 0,
    knee_deg: float = KNEE_STANDING,
    **kwargs: Any,
) -> FixtureObservation:
    """The mirror of `_bending`: posed for ARMS_UP, torso held outside FRONT_BEND's band."""
    return make_person(
        person_id=person_id,
        hip_angle_deg=TORSO_STRAIGHT,
        shoulder_angle_deg=shoulder_deg,
        knee_angle_deg=knee_deg,
        **kwargs,
    )


def _bend_cycle(*, bent_deg: float = TORSO_BENT, **kwargs: Any) -> list[FixtureObservation]:
    """Straight, bent, straight -- one complete FRONT_BEND, completed on the last frame."""
    return [_bending(deg, **kwargs) for deg in (TORSO_STRAIGHT, bent_deg, TORSO_STRAIGHT)]


def _arms_cycle(**kwargs: Any) -> list[FixtureObservation]:
    """One complete ARMS_UP, completed on the last frame."""
    return [_arms(deg, **kwargs) for deg in (ARMS_NEUTRAL, ARMS_GESTURE, ARMS_NEUTRAL)]


def _both_cycle() -> list[FixtureObservation]:
    """One figure completing the bend and the arm gesture on the very same frame."""
    return [
        make_person(hip_angle_deg=hip, shoulder_angle_deg=arm, knee_angle_deg=KNEE_STANDING)
        for hip, arm in (
            (TORSO_STRAIGHT, ARMS_NEUTRAL),
            (TORSO_BENT, ARMS_GESTURE),
            (TORSO_STRAIGHT, ARMS_NEUTRAL),
        )
    ]


def _split_bend(left_deg: float, right_deg: float) -> FixtureObservation:
    """One figure whose left hip chain measures `left_deg` and whose right measures `right_deg`.

    Both halves are `make_person` figures; only the right side's eight keypoints are swapped
    in, addressed by name, so no coordinate is ever written by hand. `make_person` poses both
    sides identically, and a rule that averages two visible sides cannot be told apart from
    one that reads either side alone unless the two sides differ.
    """
    left = _bending(left_deg)
    right = _bending(right_deg)
    swapped = tuple(
        right.keypoints_xy[index] if index in RIGHT_SIDE_INDICES else left.keypoints_xy[index]
        for index in range(KEYPOINT_COUNT)
    )
    # Confidences are identical on both figures, so only the coordinates move.
    return replace(left, keypoints_xy=swapped)


def _split_bend_cycle(left_deg: float, right_deg: float) -> list[FixtureObservation]:
    """A full bend cycle whose bent frame is asymmetric."""
    return [_bending(TORSO_STRAIGHT), _split_bend(left_deg, right_deg), _bending(TORSO_STRAIGHT)]


def _unseen(person: FixtureObservation, *indices: int) -> FixtureObservation:
    """The same figure with `indices` as YOLO reports a keypoint it never found.

    Coordinates AND confidence, together: that pairing is what makes the sentinel
    recognisable, and either one alone is a different fixture with a different meaning.
    """
    points = list(person.keypoints_xy)
    conf = list(person.keypoint_conf)
    for index in indices:
        points[index] = MISSING_POINT
        conf[index] = 0.0
    return replace(person, keypoints_xy=tuple(points), keypoint_conf=tuple(conf))


def _run(
    detector: GestureDetector,
    poses: Sequence[FixtureObservation],
    *,
    start_ms: int = 0,
    step_ms: int = 100,
) -> list[DetectionEvent]:
    """Feed one pose per frame and return every event, in emission order."""
    times = frame_sequence(len(poses), start_ms=start_ms, step_ms=step_ms)
    emitted: list[DetectionEvent] = []
    for frame_time_ms, pose in zip(times, poses, strict=True):
        emitted.extend(detector.update(frame_time_ms, pose))
    return emitted


def _per_frame(detector: GestureDetector, poses: Sequence[FixtureObservation]) -> list[int]:
    """How many events each frame produced -- the shape a totals-only assertion hides."""
    times = frame_sequence(len(poses))
    return [
        len(detector.update(frame_time_ms, pose))
        for frame_time_ms, pose in zip(times, poses, strict=True)
    ]


def _crowd_cycle(detector: GestureDetector, person_ids: Iterable[int]) -> list[DetectionEvent]:
    """Every id completes one bend cycle, all of them present in every frame."""
    emitted: list[DetectionEvent] = []
    hips = (TORSO_STRAIGHT, TORSO_BENT, TORSO_STRAIGHT)
    for frame_time_ms, hip_deg in zip(frame_sequence(3), hips, strict=True):
        for person_id in person_ids:
            emitted.extend(detector.update(frame_time_ms, _bending(hip_deg, person_id=person_id)))
    return emitted


def _types(events: Sequence[DetectionEvent]) -> list[EventType]:
    return [event.event_type for event in events]


# --------------------------------------------------------------------------
# Visibility gating
# --------------------------------------------------------------------------


def test_no_event_when_neither_side_visible() -> None:
    # Defect 1's quiet half: a person no side of whom cleared the gate is not a measurement
    # at all. No event -- and no state slot either, or the next person given this id
    # inherits a history that was never observed.
    detector = _detector()

    emitted = _run(detector, _bend_cycle(visible_conf=0.1))

    assert (emitted, set(detector.states)) == ([], set())


def test_left_only_visibility_uses_left_angle_alone() -> None:
    # DEFECT 1, head on. The right side arrives as (0, 0) sentinels; averaging them in
    # halves the readings to 85 / 50 / 85, which never rises back over `relaxing`, so the
    # gesture is armed once and never completed. Only the gated side may be averaged.
    emitted = _run(_detector(), _bend_cycle(bent_deg=SIDE_ON_BEND, visible_sides=("left",)))

    assert _types(emitted) == [EventType.FRONT_BEND]


def test_right_only_visibility_uses_right_angle_alone() -> None:
    # The mirror of the above. Both sides are tested because the original's two index lists
    # (lines 318-319) are the COCO numbering swapped, so a rewrite can easily get one side
    # right and the other silently wrong.
    emitted = _run(_detector(), _bend_cycle(bent_deg=SIDE_ON_BEND, visible_sides=("right",)))

    assert _types(emitted) == [EventType.FRONT_BEND]


def test_both_sides_visible_average_the_angles() -> None:
    # Two sides that BOTH passed the gate are averaged, and the comparison against
    # `maintaining` is strict -- so a mean landing exactly on 130 does not arm the gesture.
    # The pair is one test on purpose: reading a single side instead of the mean, or
    # softening `<` to `<=`, breaks exactly one half and leaves the other green.
    on_boundary = _run(_detector(), _split_bend_cycle(left_deg=120.0, right_deg=140.0))
    inside_band = _run(_detector(), _split_bend_cycle(left_deg=100.0, right_deg=140.0))

    assert (_types(on_boundary), _types(inside_band)) == ([], [EventType.FRONT_BEND])


@pytest.mark.parametrize(
    ("visible_conf", "expected"),
    [(0.6, []), (0.600001, [EventType.FRONT_BEND])],
    ids=["exactly-at-threshold", "just-over-threshold"],
)
def test_visibility_threshold_is_strictly_greater(
    visible_conf: float, expected: list[EventType]
) -> None:
    # `row[5] > 0.6` (line 321): the threshold value itself is NOT visible. A `>=` rewrite
    # admits keypoints the original refused and shifts the event rate on every marginal
    # detection -- a change no other test in this file would notice.
    emitted = _run(_detector(), _bend_cycle(visible_conf=visible_conf))

    assert _types(emitted) == expected


def test_sentinel_coordinates_are_skipped_even_when_confidence_passes() -> None:
    # NOT ON THE ORIGINAL TEST LIST. A keypoint whose confidence says "seen" while its
    # coordinates are (0, 0) is the model contradicting itself, not the caller making a
    # mistake -- `make_person(hidden_conf=0.9)` builds exactly that. The side is unusable and
    # is skipped as if its gate had failed. Refusing the whole frame would let one
    # inconsistent limb stop a safety detector mid-stream, and a ValueError escaping
    # `joint_angle` into the frame loop is the same failure shape as the `continue` at line
    # 310 that made the original drop a fall. The genuinely seen right side decides alone.
    emitted = _run(_detector(), _bend_cycle(visible_sides=("right",), hidden_conf=0.9))

    assert _types(emitted) == [EventType.FRONT_BEND]


def test_sentinel_coordinates_on_both_sides_emit_nothing() -> None:
    # NOT ON THE ORIGINAL TEST LIST, and the other half of the rule above: with no usable
    # side the frame decides nothing and leaves nothing behind -- the same outcome as a
    # failed gate, absent state entry included, rather than an exception.
    detector = _detector()

    emitted = _run(detector, _bend_cycle(visible_sides=(), hidden_conf=0.9))

    assert (emitted, set(detector.states)) == ([], set())


# --------------------------------------------------------------------------
# Upright precondition
# --------------------------------------------------------------------------


def test_front_bend_suppressed_when_seated() -> None:
    # What the posture gate is for: a seated worker's hip angle swings through the bend band
    # every time they lean over a bench, and none of it is a bend.
    emitted = _run(_detector(), _bend_cycle(knee_deg=KNEE_SEATED))

    assert emitted == []


@pytest.mark.parametrize(
    ("knee_deg", "expected"),
    [(160.0, []), (161.0, [EventType.FRONT_BEND])],
    ids=["exactly-at-gate", "just-over-gate"],
)
def test_upright_boundary(knee_deg: float, expected: list[EventType]) -> None:
    # `calculate_angle(...) > 160` (line 322), kept exactly: 160 degrees is not upright, 161
    # is. Both sides are pinned so an off-by-one cannot satisfy either half alone.
    emitted = _run(_detector(), _bend_cycle(knee_deg=knee_deg))

    assert _types(emitted) == expected


def test_arms_up_is_not_gated_by_upright() -> None:
    # The upright gate stands in front of the bend and nowhere else (it is line 321's block,
    # not line 358's). Hoisting it onto the detector would mute ARMS_UP for every seated or
    # crouching worker -- the one gesture a trapped worker can still make.
    emitted = _run(_detector(), _arms_cycle(knee_deg=KNEE_SEATED))

    assert _types(emitted) == [EventType.ARMS_UP]


def test_upright_requires_ankle_visibility() -> None:
    # DEFECT 2, and the one the original had no way to express: line 321 gates
    # shoulder/hip/knee and line 322 measures hip-knee-ANKLE, so the check that decides
    # whether a seated worker counts as bending ran on two keypoints whose confidence is
    # read nowhere in the file. Here the whole bend chain is visible and only the ankles are
    # missing: the gesture must be skipped, not decided on (0, 0).
    emitted = _run(_detector(), [_unseen(pose, LEFT_ANKLE, RIGHT_ANKLE) for pose in _bend_cycle()])

    assert emitted == []


def test_one_missing_ankle_leaves_the_other_side_usable() -> None:
    # NOT ON THE ORIGINAL TEST LIST. Added because the test above cannot fail against the
    # legacy behaviour: with both ankles at (0, 0) the garbage posture angle measures 30
    # degrees, which is under the gate, so "suppressed by the gate" and "suppressed by
    # garbage" look identical from outside. Here they do not. The left ankle alone is
    # missing, so the left gate fails and the right side -- fully seen, posture 175 -- must
    # decide the frame alone. Averaging the sentinel in gives 104, under the gate, and the
    # bend is lost; this is defects 1 and 2 in the same frame, and it is the common case,
    # because a worker turned even slightly away loses one ankle long before anything else.
    emitted = _run(_detector(), [_unseen(pose, LEFT_ANKLE) for pose in _bend_cycle()])

    assert _types(emitted) == [EventType.FRONT_BEND]


# --------------------------------------------------------------------------
# State machine
# --------------------------------------------------------------------------


def test_event_fires_on_cycle_completion_not_entry() -> None:
    # A gesture is a completed movement, not a posture: the event belongs to the frame the
    # worker straightens up on. Firing on entry counts a slow bend several times over.
    per_frame = _per_frame(_detector(), _bend_cycle())

    assert per_frame == [0, 0, 1]


def test_no_event_when_only_entering_the_gesture() -> None:
    # The complement of the above, asserted separately so a detector that fires on entry
    # cannot pass by emitting the right total on the wrong frames.
    per_frame = _per_frame(_detector(), [_bending(TORSO_STRAIGHT), _bending(TORSO_BENT)])

    assert per_frame == [0, 0]


def test_hysteresis_band_holds_state() -> None:
    # The 130-160 band is the anti-chatter mechanism: an angle inside it keeps whatever
    # state it found and decides nothing. Collapsing the two thresholds into one emits on
    # every wobble across it.
    poses = [
        _bending(deg)
        for deg in (TORSO_STRAIGHT, TORSO_BENT, TORSO_IN_BAND, TORSO_IN_BAND, TORSO_STRAIGHT)
    ]

    assert _per_frame(_detector(), poses) == [0, 0, 0, 0, 1]


def test_two_cycles_emit_two_events() -> None:
    # Two bends are two events, and the second one is reported on its own frame -- pinned
    # per frame so a detector that emits both at the end still fails.
    degrees = (TORSO_STRAIGHT, TORSO_BENT, TORSO_STRAIGHT, TORSO_BENT, TORSO_STRAIGHT)

    assert _per_frame(_detector(), [_bending(deg) for deg in degrees]) == [0, 0, 1, 0, 1]


def test_fresh_detector_relaxed_frame_emits_nothing() -> None:
    # `reaching` starts False: a worker who is already standing straight is not mid-gesture,
    # and their first frame is not the completion of one.
    assert _detector().update(0, _bending(TORSO_STRAIGHT)) == []


def test_fresh_detector_bent_then_straight_emits() -> None:
    # The mirror: the first frame of a person's life may be the bend itself. Requiring a
    # relaxed frame first would drop the first gesture of every appearance -- and people
    # walk into frame already bent over a load.
    per_frame = _per_frame(_detector(), [_bending(TORSO_BENT), _bending(TORSO_STRAIGHT)])

    assert per_frame == [0, 1]


def test_chatter_below_maintaining_does_not_double_emit() -> None:
    # Four frames all under `relaxing` are one gesture, whatever the angle does inside it.
    # `state_keep` exists for exactly this: the arming edge must not be re-triggerable while
    # the gesture is still being held.
    degrees = (TORSO_BENT, DEEPER_BEND, SHALLOWER_BEND, TORSO_STRAIGHT)

    assert _per_frame(_detector(), [_bending(deg) for deg in degrees]) == [0, 0, 0, 1]


def test_latch_can_re_arm_after_emitting() -> None:
    # DEFECT 6, THE HEADLINE REGRESSION. Replayed over 986 frames of real footage the
    # original emitted zero ARMS_UP and zero FRONT_BEND while its visibility gates passed
    # 811 and 964 times: every slot latched once and went silent for the life of the
    # process. Three consecutive cycles, asserted per frame, so a latch that emits once and
    # stops -- or one that stops after two -- fails on the count and on the position.
    degrees = [TORSO_STRAIGHT]
    for _ in range(3):
        degrees += [TORSO_BENT, TORSO_IN_BAND, TORSO_STRAIGHT]

    per_frame = _per_frame(_detector(), [_bending(deg) for deg in degrees])

    assert per_frame == [0, 0, 0, 1, 0, 0, 1, 0, 0, 1]


def test_state_is_held_across_a_frame_with_no_visible_side() -> None:
    # NOT ON THE ORIGINAL TEST LIST. A worker who turns side-on for a few frames mid-bend has
    # not stopped bending, and dropping the half-completed cycle would lose gestures to
    # ordinary occlusion -- the same class of silent loss as the latch that never re-armed.
    # A frame with no usable side decides nothing and changes nothing, so the bend still
    # completes when the worker straightens. `forget` is the sanctioned way to discard a
    # person's state; occlusion is not, and the two must not be conflated.
    #
    # The occluded frame is posed STRAIGHT on purpose: an implementation that measures
    # ungated coordinates releases on frame 2 and reports [0, 1, 0] instead.
    poses = [
        _bending(TORSO_BENT),
        _bending(TORSO_STRAIGHT, visible_conf=0.1),
        _bending(TORSO_STRAIGHT),
    ]

    assert _per_frame(_detector(), poses) == [0, 0, 1]


# --------------------------------------------------------------------------
# Multi-person
# --------------------------------------------------------------------------


def test_two_people_have_independent_state() -> None:
    # DEFECT 5. Person 1 stands still for the whole sequence while person 0 bends and
    # straightens. Sharing one state means person 1's straight frames release person 0's
    # arming edge, and the single event that comes out carries person 1's confidence
    # instead -- which is why the two boxes are given different confidences here.
    detector = _detector()
    emitted: list[DetectionEvent] = []
    hips = (TORSO_STRAIGHT, TORSO_BENT, TORSO_STRAIGHT)

    for frame_time_ms, hip_deg in zip(frame_sequence(3), hips, strict=True):
        bender = _bending(hip_deg, person_id=0, detection_confidence=BENDER_CONF)
        bystander = _bending(TORSO_STRAIGHT, person_id=1, detection_confidence=BYSTANDER_CONF)
        emitted.extend(detector.update(frame_time_ms, bender))
        emitted.extend(detector.update(frame_time_ms, bystander))

    assert [(event.event_type, event.confidence) for event in emitted] == [
        (EventType.FRONT_BEND, BENDER_CONF)
    ]


def test_eleven_people_do_not_raise_index_error() -> None:
    # DEFECT 4: `angle = [0] * 10` and five siblings, so the eleventh person in frame is an
    # IndexError that kills the frame loop. A crowded site is the case this system is for.
    emitted = _crowd_cycle(_detector(), range(11))

    assert _types(emitted) == [EventType.FRONT_BEND] * 11


def test_twenty_people_all_tracked() -> None:
    # DEFECT 3: `numberOfPerson = len(checkNodeVisibility[0])` counts KEYPOINTS -- it is 17
    # for any crowd -- and `personIndex` wraps against it, so person 18 was scored against
    # person 1's history. Nothing in this module may be bounded by 17.
    emitted = _crowd_cycle(_detector(), range(20))

    assert _types(emitted) == [EventType.FRONT_BEND] * 20


def test_sparse_non_contiguous_ids() -> None:
    # Tracker ids are not indices: they are handed out as people enter and are not reused,
    # so by mid-shift they are large and full of holes. A list-backed state is an IndexError
    # here however long the list was made.
    emitted = _crowd_cycle(_detector(), (7, 99, 1000))

    assert _types(emitted) == [EventType.FRONT_BEND] * 3


def test_states_keyed_by_person_id() -> None:
    # The public evidence that a slot belongs to a person rather than to a position in
    # YOLO's output. Two people seen in one frame are two entries under their own ids.
    detector = _detector()
    detector.update(0, _bending(TORSO_BENT, person_id=3))
    detector.update(0, _bending(TORSO_BENT, person_id=5))

    assert set(detector.states) == {3, 5}


def test_forget_resets_state() -> None:
    # `forget` is what the caller runs when a person leaves the frame. Without it the state
    # of everyone who ever appeared is held for the life of the process; with a partial one,
    # the next person given id 3 inherits a half-completed gesture and emits it on their
    # first straight frame. All three properties are asserted together: 5 survives, the
    # stale half-cycle is gone, and a fresh cycle for 3 still works.
    detector = _detector()
    detector.update(0, _bending(TORSO_BENT, person_id=3))
    detector.update(0, _bending(TORSO_BENT, person_id=5))

    detector.forget({3})
    remaining = set(detector.states)
    stale = detector.update(100, _bending(TORSO_STRAIGHT, person_id=3))
    fresh = _run(
        detector,
        [_bending(deg, person_id=3) for deg in (TORSO_BENT, TORSO_STRAIGHT)],
        start_ms=200,
    )

    assert (remaining, stale, _types(fresh)) == ({5}, [], [EventType.FRONT_BEND])


# --------------------------------------------------------------------------
# Payload
# --------------------------------------------------------------------------


def test_confidence_is_detection_confidence_not_keypoint_visibility() -> None:
    # DEFECT 7: `"confidencePercentage": row[11]` (line 343) published a keypoint
    # VISIBILITY score as the detector's confidence in the event. They are different numbers
    # about different things, and this one is multiplied by 100 and shown to a safety
    # officer. The keypoint scores here are deliberately just over the 0.6 gate so a
    # detector that still reads them reports 0.61.
    emitted = _run(_detector(), _bend_cycle(visible_conf=0.61, detection_confidence=0.93))

    assert [event.confidence for event in emitted] == [0.93]


def test_confidence_correct_when_gate_passes_via_right_branch() -> None:
    # DEFECT 7's nastier half: when the `or` at line 321 passed through its RIGHT-hand
    # branch, indices 11 and 7 were constrained by nothing at all, so the number published
    # was whatever sat in the unseen side's row -- 0.0 for this person, a confident-looking
    # "0%" on the dashboard. Left side hidden, right side at 0.99, box at 0.88.
    emitted = _run(
        _detector(),
        _bend_cycle(visible_sides=("right",), visible_conf=0.99, detection_confidence=0.88),
    )

    assert [event.confidence for event in emitted] == [0.88]


def test_start_time_is_the_injected_frame_time() -> None:
    # `int(time.time() * 1000)` (line 341) stamped the wall clock at emit time, so replaying
    # a recorded file dated every event today and no baseline could be reproduced. The stamp
    # is the frame's own time, and it is the frame the gesture COMPLETED on -- the third one
    # here, not the first or the one the bend started on.
    detector = _detector()
    times = (1_700_000_000_000, 1_700_000_000_100, 1_700_000_000_200)
    emitted: list[DetectionEvent] = []

    for frame_time_ms, hip_deg in zip(
        times, (TORSO_STRAIGHT, TORSO_BENT, TORSO_STRAIGHT), strict=True
    ):
        emitted.extend(detector.update(frame_time_ms, _bending(hip_deg)))

    assert [event.start_time_ms for event in emitted] == [1_700_000_000_200]


def test_gesture_events_carry_no_time_period() -> None:
    # ARMS_UP and FRONT_BEND are countable: `RawEventService.listener` stores them
    # unconditionally and never reads a duration, while `/event/periodic-events` SUMS
    # `timePeriod` over whatever carries one. A gesture that sent a duration would be
    # aggregated as if it were a PPE violation.
    emitted = _run(_detector(), _bend_cycle())

    assert [event.time_period_ms for event in emitted] == [None]


def test_camera_name_comes_from_constructor() -> None:
    # The original sent `args.input` -- a device index or a file path -- as `cameraName`,
    # and that field is the only thing the dashboard groups violations by site with.
    emitted = _run(_detector(camera_name="kuzey-kapisi"), _bend_cycle())

    assert [event.camera_name for event in emitted] == ["kuzey-kapisi"]


def test_both_gestures_can_emit_on_one_frame() -> None:
    # A worker straightening up as their arms come down completes both gestures on one
    # frame; the original ran them as two independent `if` blocks over one shared
    # `personIndex`, so nothing said what order they came out in. Order is the CONFIGURED
    # order, which is why the same figure is run through a reversed gesture tuple: a
    # detector that hardcodes the sequence, or sorts by name, passes only the first half.
    gestures = Config().gestures

    forwards = _run(_detector(gestures=gestures), _both_cycle())
    backwards = _run(_detector(gestures=tuple(reversed(gestures))), _both_cycle())

    assert (_types(forwards), _types(backwards)) == (
        [EventType.ARMS_UP, EventType.FRONT_BEND],
        [EventType.FRONT_BEND, EventType.ARMS_UP],
    )


# --------------------------------------------------------------------------
# Constructor wiring
#
# NOT ON THE ORIGINAL TEST LIST. Every test above runs on the default 0.6 gate, the default
# 160-degree posture angle and the default upright chains, so an implementation that
# hardcodes all four passes the whole file. These four pin that each argument reaches the
# decision it names -- the gap `test_ppe_rules.py` closed for `grace_ms`.
# --------------------------------------------------------------------------


def test_keypoint_visibility_threshold_comes_from_the_constructor() -> None:
    # A site with a poorly placed camera is retuned by raising this gate, and a detector that
    # ignores the new value keeps admitting the keypoints the operator just excluded --
    # silently, because the events still look plausible. 0.7 clears the 0.6 default and not
    # the 0.8 asked for here; 0.85 clears both, so only a hardcoded gate answers alike.
    detector_kwargs = {"keypoint_visibility": STRICT_VISIBILITY}
    under = _run(_detector(**detector_kwargs), _bend_cycle(visible_conf=UNDER_STRICT_GATE))
    over = _run(_detector(**detector_kwargs), _bend_cycle(visible_conf=OVER_STRICT_GATE))

    assert (_types(under), _types(over)) == ([], [EventType.FRONT_BEND]), (
        f"{UNDER_STRICT_GATE} keypoints must fail a {STRICT_VISIBILITY} gate; a hardcoded "
        "0.6 admits them and both halves come out identical."
    )


def test_upright_angle_comes_from_the_constructor() -> None:
    # A 120-degree crouch is not upright under the default 160 and is under the 100 asked for
    # here; a 90-degree sit is under neither. Both halves are needed: an implementation that
    # ignores the argument fails the first, and one that drops the posture check altogether
    # -- the tempting simplification, since it makes the seated tests' twin pass -- fails
    # the second.
    crouched = _run(_detector(upright_angle=LOW_UPRIGHT_GATE), _bend_cycle(knee_deg=KNEE_CROUCHED))
    seated = _run(_detector(upright_angle=LOW_UPRIGHT_GATE), _bend_cycle(knee_deg=KNEE_SEATED))

    assert (_types(crouched), _types(seated)) == ([EventType.FRONT_BEND], [])


def test_upright_chains_come_from_the_constructor() -> None:
    # The two chains have to be READ, not decoration. Both are wired to the arm --
    # hip, shoulder, elbow -- so the posture decision is taken from a joint the default
    # triples never touch, and the knee is set to contradict it in both directions: a seated
    # 90-degree knee with a straight arm must still emit, and a standing 175-degree knee with
    # a folded arm must not. An implementation that ignores either argument keeps one default
    # triple, averages the knee back in and fails both halves.
    #
    # This pairing is deliberately not a configuration `Config` would accept -- it refuses a
    # gesture whose visibility gate does not cover the upright chain, and FRONT_BEND's gate
    # does not cover the elbow. `GestureDetector` takes the chains as plain arguments, and
    # what is under test is those arguments reaching the measurement.
    chains: dict[str, Any] = {
        "upright_left_idx": (LEFT_HIP, LEFT_SHOULDER, LEFT_ELBOW),
        "upright_right_idx": (RIGHT_HIP, RIGHT_SHOULDER, RIGHT_ELBOW),
    }

    arm_straight = _run(
        _detector(**chains), _bend_cycle(knee_deg=KNEE_SEATED, shoulder_deg=ARMS_NEUTRAL)
    )
    arm_folded = _run(
        _detector(**chains), _bend_cycle(knee_deg=KNEE_STANDING, shoulder_deg=ARMS_GESTURE)
    )

    assert (_types(arm_straight), _types(arm_folded)) == ([EventType.FRONT_BEND], [])


# --------------------------------------------------------------------------
# Degenerate input
#
# Constructed through `pose_rules.PersonObservation` directly rather than through
# `make_person`, which refuses to build a malformed figure at all: these two pin that the
# real value object refuses it as well, at construction, where the traceback still points
# at the adapter that sliced the rows wrong.
# --------------------------------------------------------------------------


def test_wrong_keypoint_count_raises() -> None:
    # A pose model that is not COCO-17, or a row sliced wrong on the way in, must fail where
    # the shape is wrong. Every keypoint downstream is addressed by a bare integer, so a
    # 16-long row silently turns "left hip" into an elbow from index 11 onward.
    figure = _bending(TORSO_STRAIGHT)

    with pytest.raises(ValueError):
        PersonObservation(
            person_id=0,
            keypoints_xy=figure.keypoints_xy[:-1],
            keypoint_conf=figure.keypoint_conf[:-1],
            detection_confidence=0.9,
        )


def test_mismatched_xy_and_conf_lengths_raise() -> None:
    # 17 coordinates against 16 scores means the two are misaligned, and every visibility
    # gate then reads the confidence of a joint it is not measuring -- a silent, sideways
    # form of the swapped-index defect at lines 318-319.
    figure = _bending(TORSO_STRAIGHT)

    with pytest.raises(ValueError):
        PersonObservation(
            person_id=0,
            keypoints_xy=figure.keypoints_xy,
            keypoint_conf=figure.keypoint_conf[:-1],
            detection_confidence=0.9,
        )
