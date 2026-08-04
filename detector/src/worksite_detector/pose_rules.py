"""Countable gesture events -- ARMS_UP and FRONT_BEND -- from one person's pose keypoints.

This module replaces ``aiModule.py`` lines 312-398, the densest defect cluster in the
original: seven confirmed defects in 86 lines. Each decision documented below is one of them
inverted, and ``tests/test_pose_rules.py`` pins every one.

**A gesture is a completed movement, so the event fires on the release edge.** Each gesture
is a hysteresis band on a single joint angle: the cycle *arms* when the angle first falls
below ``maintaining``, and *completes* when it rises back above ``relaxing``. The event is
stamped with the frame time of the completion, not of the entry. Firing on entry would
count one slow movement once per frame it was held -- at the ten frames a second the
original ran at, a worker stooping over a load for two seconds reports twenty FRONT_BENDs --
and the dashboard counts occurrences per day, so the number it shows would be a function of
frame rate rather than of what anyone did. An angle *inside* the band decides nothing and
keeps whatever state it found, which is what stops a limb wavering across a single
threshold from chattering out an event per frame.

**The latch re-arms, and that is the headline fix.** The stored state is one bit per gesture
per person, and it returns to its resting value on every completion, so arm-complete-arm-
complete continues for as long as the person is tracked. The original could not: a slot that
armed was released only by an angle over ``relaxing``, and defect 1 below meant that angle
never came. Replayed over 986 frames of real footage it emitted **zero** ARMS_UP and **zero**
FRONT_BEND -- not for want of input, since its visibility gates passed 811 and 964 times.
Every slot armed once and went silent for the life of the process. A future reader looking at
the state machine below will see a one-shot latch plus a reset and be tempted to drop the
reset; that reset is the difference between this feature working and not existing.

**Only the sides that passed their own gate are averaged.** The visibility gates at lines 321
and 358 are ``left AND ... or right AND ...``, and ``calculate_angle`` then averaged *both*
sides whatever the gate decided. A worker standing side-on has the unseen side reported as
YOLO's ``(0, 0)`` sentinel, ``atan2(0, 0)`` is ``0.0`` rather than an error, and that zero
was folded in -- roughly halving every angle before it met a threshold, which is also why the
latch above never released. Here each side is gated on its own confidences, measured on its
own, and the mean is taken over the sides that survived; one usable side decides alone, and
``geometry.joint_angle`` refuses the sentinel outright as the backstop.

**The posture precondition is measured over the chain the caller names.** Line 321 gated
shoulder-hip-knee and line 322 then measured hip-knee-**ankle**; ankle confidence, indices 15
and 16, is read nowhere in that file, so the check that stops a seated worker counting as
bending was itself computed from two sentinels. The chain and its angle are constructor
arguments here, and ``Config`` refuses a gesture whose visibility gate does not cover the
upright chain -- so the gate that admits a side is the gate that covers everything measured
from it. The precondition is per gesture (``GestureSpec.requires_upright``) and not a
property of the detector: it stands in front of the bend and nowhere else, and hoisting it
would mute ARMS_UP for every seated or crouching worker, which is the one gesture a trapped
worker can still make.

**State is keyed by an externally supplied person id.** The original indexed three parallel
lists by a person's position in YOLO's output for that frame, with no tracker of any kind, so
slot 0's history routinely belonged to a different human on the next frame -- unbounded by
crowd size and needing only two people to happen. The lists were ``[False] * 10``, so the
eleventh person in frame was an IndexError that took the frame loop with it, and the bound
they were wrapped against, ``numberOfPerson``, was a *keypoint* count and therefore 17 for
any crowd. A dict keyed by ``PersonObservation.person_id`` makes the owner of a slot
explicit, accepts sparse and arbitrarily large ids as a real tracker hands them out, and is
bounded by nothing. Identity cannot be recovered from a single frame of pose keypoints, so
this module names the requirement in its signature rather than inventing one.

The corollary is that an entry leaves only through ``forget``. A frame in which no side of a
person is usable decides nothing and changes nothing: a worker who turns side-on for a few
frames mid-bend has not stopped bending, and discarding the half-completed cycle would lose
gestures to ordinary occlusion -- the same class of silent loss as the latch that never
re-armed. From inside this module an occluded frame and a departure are indistinguishable,
so the caller, which has the tracker, is the one that says a person is gone.

**The published confidence is the person box's.** ``row[11]`` and ``row[7]`` were sent as
``confidencePercentage``, which is a keypoint *visibility* score: a different number about a
different thing, multiplied by 100 and shown to a safety officer as the detector's confidence
in the event. Worse, when the ``or`` passed through its right-hand branch those two indices
were constrained by nothing, so what reached the engine could be the near-zero score of a
limb that was never seen. ``detection_confidence`` is carried on the observation and
published verbatim.

**Duplicate and backwards ``frame_time_ms`` are deliberately unguarded**, the same call
``ppe_rules`` makes. ``update`` stamps an event with whatever frame time it was handed and
takes no state decision from the clock, so camera clock skew or a reordered frame yields a
mis-stamped event rather than an exception inside a real-time loop. Adding a raise here would
stop the detector over a mislabelled millisecond.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from worksite_detector.config import GestureSpec
from worksite_detector.events import DetectionEvent, EventType
from worksite_detector.geometry import Point, joint_angle

# A COCO pose model reports 17 keypoints, indices 0-16, and every index in a
# GestureSpec or an upright chain is a bare integer addressed into that row.
_COCO_KEYPOINT_COUNT = 17

#: One three-point chain, ``[end, vertex, end]``, as ``geometry.joint_angle`` takes it.
_Chain = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class PersonObservation:
    """One person in one frame: where their joints are, and how sure the model is.

    Frozen because a frame is a record of something that already happened; the rules read it
    and never correct it.

    Attributes:
        person_id: Stable identity of this person across frames, from whatever tracker the
            adapter runs. It is the key of this person's gesture state, so ids that are
            reused for a different human silently transplant a half-completed gesture, and
            ids that change every frame mean no gesture ever completes.
        keypoints_xy: Exactly 17 ``(x, y)`` pairs in COCO order, in image pixels. A keypoint
            the model did not find arrives as ``(0.0, 0.0)`` and is refused by
            ``geometry.joint_angle`` rather than measured.
        keypoint_conf: Exactly 17 per-keypoint visibility scores, index-aligned with
            ``keypoints_xy``. These feed the visibility gate and nothing else -- in
            particular they are never published.
        detection_confidence: Confidence of the person *box*, in [0, 1]. This is what is
            published as the event's ``confidencePercentage``; see the module docstring for
            the number it replaces.
    """

    person_id: int
    keypoints_xy: tuple[Point, ...]
    keypoint_conf: tuple[float, ...]
    detection_confidence: float

    def __post_init__(self) -> None:
        # Checked at construction, where the traceback still points at the adapter that
        # sliced the model's rows, rather than at the frame loop that read them.
        if len(self.keypoints_xy) != _COCO_KEYPOINT_COUNT:
            raise ValueError(
                f"keypoints_xy must hold {_COCO_KEYPOINT_COUNT} (x, y) pairs in COCO order, "
                f"got {len(self.keypoints_xy)}. Every keypoint downstream is addressed by a "
                "bare integer, so a short row turns 'left hip' into an elbow from index 11 on."
            )
        if len(self.keypoint_conf) != _COCO_KEYPOINT_COUNT:
            raise ValueError(
                f"keypoint_conf must hold {_COCO_KEYPOINT_COUNT} scores, one per keypoint, got "
                f"{len(self.keypoint_conf)}. The two rows are index-aligned; misaligned, every "
                "visibility gate reads the confidence of a joint it is not measuring."
            )
        if not 0.0 <= self.detection_confidence <= 1.0:
            raise ValueError(
                f"detection_confidence must be a fraction in [0.0, 1.0], got "
                f"{self.detection_confidence!r}. It is published verbatim, so an out-of-range "
                "value raises out of DetectionEvent thousands of frames from its cause."
            )


@dataclass(slots=True)
class PersonState:
    """Where one tracked person stands in each gesture's hysteresis cycle.

    One bit per gesture: True while that gesture is armed -- the angle has fallen below
    ``maintaining`` and has not yet risen back above ``relaxing``. A gesture this person has
    never been measured for is absent, which reads as False.

    That single bit replaces four parallel arrays in the original. ``angle`` held a
    measurement that is recomputed every frame and is not state at all; ``reaching`` and
    ``reaching_last`` were the same bit one frame apart, and only the older of the two needs
    keeping; and ``state_keep`` guarded a re-arm that the edge comparison already prevents,
    because the bit reaches True only by crossing ``maintaining`` from below.

    Mutable and unsynchronised, matching the single-threaded frame loop that owns it.
    """

    reaching: dict[EventType, bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _SideReading:
    """One side of one person that is fit to take part in a gesture decision.

    A side exists here only if every keypoint its gate names cleared the visibility
    threshold *and* every chain measured from it yielded an angle. ``upright_angle`` is None
    for a gesture that requires no posture precondition, and never None for one that does.
    """

    gesture_angle: float
    upright_angle: float | None


def _mean(values: Sequence[float]) -> float:
    """The plain mean of one or more angles, in degrees.

    Only ever called with the sides that passed their own gate, which is the whole point:
    the original averaged two sides unconditionally and the unseen one contributed a zero.
    """
    return sum(values) / len(values)


class GestureDetector:
    """Turns per-person pose keypoints into countable gesture events.

    Feed every person of every frame to ``update``, and call ``forget`` with the ids the
    tracker has dropped. One instance per camera: the camera name is published on every
    event and is how the dashboard attributes a violation to a site.

    The state is mutable and unsynchronised, matching the single-threaded frame loop that
    owns it.
    """

    def __init__(
        self,
        gestures: Sequence[GestureSpec],
        camera_name: str,
        keypoint_visibility: float = 0.6,
        upright_left_idx: _Chain = (11, 13, 15),
        upright_right_idx: _Chain = (12, 14, 16),
        upright_angle: float = 160.0,
    ) -> None:
        """Configure a detector.

        ``gestures`` fixes both which gestures are recognised and the order events are
        emitted in when one frame completes more than one; it is copied to a tuple so a
        caller holding the sequence cannot retune the detector mid-run. Every other argument
        is a number the original spelled inline: ``keypoint_visibility`` is its ``> 0.6``
        gate, applied per side and strictly, and ``upright_left_idx`` / ``upright_right_idx``
        / ``upright_angle`` are the posture precondition its ``> 160`` check meant to be.

        Nothing is validated here. ``Config`` is the validating layer -- it enforces the
        hysteresis band, the keypoint range and the rule that a gesture's gate must cover the
        upright chain -- and re-checking those from a second place would report the same
        mistake from a worse one. Taking the chains as plain arguments is also what lets a
        test point the posture decision at a joint the defaults never touch, and so prove
        that the argument reaches the measurement at all.
        """
        self._gestures = tuple(gestures)
        self._camera_name = camera_name
        self._keypoint_visibility = keypoint_visibility
        self._upright_left_idx = upright_left_idx
        self._upright_right_idx = upright_right_idx
        self._upright_angle = upright_angle
        self._states: dict[int, PersonState] = {}

    @property
    def states(self) -> Mapping[int, PersonState]:
        """Every person currently carrying gesture state, by id.

        A read-only view of the live mapping, not a copy: it is here so a caller can see
        which ids are held -- and therefore which need forgetting -- without being able to
        edit a hysteresis cycle from outside the state machine that owns it.
        """
        return MappingProxyType(self._states)

    def update(self, frame_time_ms: int, observation: PersonObservation) -> list[DetectionEvent]:
        """Record one person on one frame and return the gestures they completed on it.

        Called once per person per frame, in any order; people are independent because each
        one's state is keyed by ``observation.person_id``. Most frames return an empty list.
        A frame returns one event per gesture whose cycle completed on it, in the order
        ``gestures`` was configured in -- a worker straightening up as their arms come down
        completes both on the same frame, and the order is the caller's to fix.

        ``observation`` is read by attribute and is never type-checked: the four field names
        are the contract, so any object carrying them is a valid frame. ``frame_time_ms``
        stamps the events this call emits and is otherwise not interpreted; see the module
        docstring on duplicate and backwards timestamps.

        A gesture takes no decision at all -- and leaves this person's state untouched -- on
        a frame where neither side cleared its visibility gate, where neither side could be
        measured, or where the posture precondition it requires was not met. A person who has
        never reached a decision has no entry in ``states``.
        """
        emitted: list[DetectionEvent] = []
        state: PersonState | None = None

        for spec in self._gestures:
            readings = self._read_sides(spec, observation)
            if not readings:
                continue

            if spec.requires_upright:
                posture = _mean(
                    [side.upright_angle for side in readings if side.upright_angle is not None]
                )
                # Strictly greater, exactly as line 322 had it: 160 degrees is not upright.
                if not posture > self._upright_angle:
                    continue

            angle = _mean([side.gesture_angle for side in readings])
            if state is None:
                # Created on the first decision this frame, never on arrival: a person no
                # side of whom was measurable is not an observation, and an entry made for
                # them would hand the next person given this id a history nobody saw.
                state = self._states.setdefault(observation.person_id, PersonState())

            was_reaching = state.reaching.get(spec.event_type, False)
            if angle < spec.maintaining:
                now_reaching = True
            elif angle > spec.relaxing:
                now_reaching = False
            else:
                # Inside the hysteresis band. Neither threshold is met, so the frame holds
                # whatever state it found; this is the anti-chatter mechanism itself, and
                # collapsing the two thresholds into one emits on every wobble across it.
                now_reaching = was_reaching
            state.reaching[spec.event_type] = now_reaching

            if was_reaching and not now_reaching:
                # The release edge, and the only place an event is born. The bit is already
                # back at rest, so the very next fall below `maintaining` arms the next
                # repetition -- see the module docstring for what a one-shot latch cost.
                emitted.append(
                    DetectionEvent(
                        event_type=spec.event_type,
                        start_time_ms=frame_time_ms,
                        confidence=observation.detection_confidence,
                        camera_name=self._camera_name,
                        # Countable, so no duration: `/event/periodic-events` SUMS
                        # timePeriod over whatever carries one, and a gesture that sent a
                        # duration would be aggregated as if it were a PPE violation.
                        time_period_ms=None,
                    )
                )

        return emitted

    def forget(self, person_ids: Collection[int]) -> None:
        """Discard the gesture state of everyone in ``person_ids``.

        What the caller runs when the tracker drops an id. Without it the state of everyone
        who ever appeared is held for the life of the process, and the next person handed a
        reused id inherits a half-completed gesture and emits it on their first straight
        frame.

        Ids with no state are ignored rather than refused: the caller's natural argument is
        the difference between two frames' id sets, and raising over an id that had never
        reached a decision -- a person seen only side-on, say -- would stop the frame loop
        over housekeeping.
        """
        for person_id in person_ids:
            self._states.pop(person_id, None)

    def _read_sides(self, spec: GestureSpec, observation: PersonObservation) -> list[_SideReading]:
        """The sides of ``observation`` fit to decide ``spec`` on this frame, left first."""
        upright_left = self._upright_left_idx if spec.requires_upright else None
        upright_right = self._upright_right_idx if spec.requires_upright else None
        candidates = (
            self._read_side(
                observation, spec.left_points_idx, spec.left_visibility_idx, upright_left
            ),
            self._read_side(
                observation, spec.right_points_idx, spec.right_visibility_idx, upright_right
            ),
        )
        return [reading for reading in candidates if reading is not None]

    def _read_side(
        self,
        observation: PersonObservation,
        gesture_chain: _Chain,
        visibility_chain: tuple[int, ...],
        upright_chain: _Chain | None,
    ) -> _SideReading | None:
        """Measure one side, or None if it is not fit to take part in the decision.

        Two ways to be unfit, and they are the same answer on purpose. The gate is an AND
        over every keypoint the side names -- the original's ``or`` is what let a side-on
        person through with half a skeleton -- and it is strictly greater than the threshold,
        as ``row[5] > 0.6`` was, so the threshold value itself is still excluded.

        A side that clears the gate and *then* fails to measure is the model contradicting
        itself: a confidence saying "seen" over the ``(0, 0)`` sentinel. That is not the
        caller's mistake and it is not fatal. Letting the ValueError escape into the frame
        loop is the same failure shape as the ``continue`` at line 310 that made the original
        drop a fall, so the side is skipped exactly as if its gate had failed and the
        genuinely seen side decides alone. If neither side survives, the frame decides
        nothing at all -- which is the honest reading, since nothing was observed.
        """
        if not all(
            observation.keypoint_conf[index] > self._keypoint_visibility
            for index in visibility_chain
        ):
            return None

        try:
            gesture_angle = _angle_of(observation, gesture_chain)
            # Measured on this side and averaged only with the other side's, so the posture
            # precondition is decided by the same limbs that were confirmed present.
            upright_angle = None if upright_chain is None else _angle_of(observation, upright_chain)
        except ValueError:
            return None

        return _SideReading(gesture_angle=gesture_angle, upright_angle=upright_angle)


def _angle_of(observation: PersonObservation, chain: _Chain) -> float:
    """The angle at ``chain``'s middle keypoint.

    Raises:
        ValueError: If any of the three keypoints is unusable -- the ``(0, 0)`` sentinel, a
            NaN or an infinity. ``geometry.joint_angle`` refuses each rather than returning
            the plausible-looking number that hid the original defect for so long.
    """
    return joint_angle([observation.keypoints_xy[index] for index in chain])
