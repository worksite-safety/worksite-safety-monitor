"""Stick figures with exact joint angles, for the pose rules to be tested against.

Every pose test in this suite is a sentence of the form "a frame in which the hip
angle is 120 degrees". `make_person` is what turns that sentence into the 17
pixel coordinates a rule actually sees, so if it is wrong the whole pose suite is
green and proves nothing. `tests/test_support.py` measures its output back
through `worksite_detector.geometry.joint_angle` -- the same function the rules
use -- and that round trip is the only thing making the fixtures trustworthy.

Coordinate convention
---------------------
Image coordinates, as they come out of YOLO: `x` grows to the right, `y` grows
**downward**, the origin is the top-left corner of the frame, and the units are
pixels. To keep the arithmetic below readable, every limb is placed by a
*bearing* measured the way a reader sees it on screen -- counter-clockwise from
the +x axis, so 0 points right, 90 points straight **up the screen** and -90
points straight down -- and `_place` converts that to image coordinates by
subtracting the sine instead of adding it. That single minus sign is the entire
y-flip. It exists so the numbers read naturally (the shoulder has a *smaller* y
than the hip, because it is higher in the frame); it cannot change any measured
angle, because flipping y is a reflection and reflections preserve the unsigned
angle `joint_angle` returns.

How a chain is made to measure an exact angle
---------------------------------------------
The figure is built outward from the hip, each segment's bearing defined
*relative to the segment it hangs off*:

    thigh      bearing -90                    (straight down; the leg is planted)
    torso      bearing -90 + hip_angle        (rotates about the hip, so the
                                               shoulder-hip-knee angle IS the
                                               requested one, by construction)
    shin       bearing (knee->hip) - knee_angle
    upper arm  bearing (shoulder->hip) + shoulder_angle
    forearm    collinear with the upper arm   (a straight arm; no rule reads it)

The angle at a joint is the separation of the two bearings leaving it, and each
of the three is set directly by one parameter -- so each chain measures its own
argument exactly, and the three are **independent** even though they share the
hip, the shoulder and the knee. Bending at the hip swings the torso, arm and
head as one rigid piece, which changes where the elbow is but not the angle at
the shoulder; that is what a real body does, and it is why changing one
parameter cannot perturb another chain's measurement.

Angles increase toward +x throughout: the subject faces right, bends forward to
the right, and raises the arm forward. The lengths below are ordinary pixel
sizes for a person a few metres from a camera. None of the constants matter to
any rule -- `joint_angle` is translation- and scale-invariant -- so they are
chosen only to make a debug print of the figure recognisable.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from tests._support.keypoints import (
    KEYPOINT_COUNT,
    KEYPOINT_NAMES,
    LEFT_ANKLE,
    LEFT_EAR,
    LEFT_ELBOW,
    LEFT_EYE,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    LEFT_SIDE_INDICES,
    LEFT_WRIST,
    NOSE,
    RIGHT_ANKLE,
    RIGHT_EAR,
    RIGHT_ELBOW,
    RIGHT_EYE,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    RIGHT_SIDE_INDICES,
    RIGHT_WRIST,
)

Point = tuple[float, float]

# --------------------------------------------------------------------------
# Figure proportions, in pixels. Arbitrary but fixed: a test that depends on any
# of these numbers is testing the fixture, not the rule.
# --------------------------------------------------------------------------
HIP_X = 300.0
HIP_Y = 400.0

#: Horizontal gap between the subject's two sides. Only there so the two sides
#: are distinguishable in a debug dump; both sides are built with identical
#: angles, and a translation cannot change an angle.
SIDE_SEPARATION_PX = 40.0

TORSO_PX = 120.0
THIGH_PX = 110.0
SHIN_PX = 110.0
UPPER_ARM_PX = 70.0
FOREARM_PX = 65.0

# Head keypoints sit on the torso axis above the shoulder. Placing the ear
# exactly on the hip->shoulder ray is deliberate: `sport_list['frontbending']`
# in aiModule.py measures ear-hip-knee where `sport_list['bending']` measures
# shoulder-hip-knee, so this makes both readings equal `hip_angle_deg` and the
# fixture stays correct whichever chain the rule under test picks. The eye is
# decorative -- no rule reads it.
EAR_RISE_PX = 45.0
EYE_RISE_PX = 62.0
NOSE_RISE_PX = 55.0

#: YOLO writes literal (0, 0) for a keypoint it did not find; `joint_angle`
#: refuses that sentinel rather than measuring it.
MISSING_POINT: Point = (0.0, 0.0)


@dataclass(frozen=True, slots=True)
class PersonObservation:
    """One person in one frame: where their joints are and how sure the model is.

    A stand-in for the real value object, which belongs to `pose_rules` and is
    not written yet. The pose rules must accept this shape.

    Attributes:
        person_id: Index of this person within the frame, as YOLO orders them.
        keypoints_xy: Exactly 17 `(x, y)` pairs in COCO order, in image pixels.
            A keypoint the model did not find is `(0.0, 0.0)`.
        keypoint_conf: Exactly 17 per-keypoint visibility scores in [0, 1],
            index-aligned with `keypoints_xy`. This is what `aiModule.py`
            compares against 0.6 at lines 321 and 358.
        detection_confidence: Confidence of the person detection as a whole, in
            [0, 1]. Distinct from `keypoint_conf`: the original published a
            keypoint visibility score as the event's `confidencePercentage`
            (lines 343 and 382), which is the number this field exists to
            replace.
    """

    person_id: int
    keypoints_xy: tuple[Point, ...]
    keypoint_conf: tuple[float, ...]
    detection_confidence: float

    def __post_init__(self) -> None:
        # A fixture that silently returns 16 keypoints would make every rule
        # test downstream fail somewhere far from the cause.
        if len(self.keypoints_xy) != KEYPOINT_COUNT:
            raise ValueError(
                f"keypoints_xy must hold {KEYPOINT_COUNT} (x, y) pairs in COCO order, "
                f"got {len(self.keypoints_xy)}"
            )
        if len(self.keypoint_conf) != KEYPOINT_COUNT:
            raise ValueError(
                f"keypoint_conf must hold {KEYPOINT_COUNT} scores, one per keypoint, "
                f"got {len(self.keypoint_conf)}"
            )


@dataclass(frozen=True, slots=True)
class ObjectDetection:
    """One box from the PPE model: `no-helmet`, `no-jacket` or `fall`.

    `box` is `(x1, y1, x2, y2)` in image pixels -- the `xyxy` form
    `aiModule.py` line 295 unpacks. No rule reads it today; it is carried so a
    fixture can be told apart from another in a failure message.
    """

    label: str
    confidence: float
    box: tuple[float, float, float, float]


def _place(origin: Point, bearing_deg: float, length: float) -> Point:
    """The point `length` pixels from `origin` along `bearing_deg`.

    The bearing is counter-clockwise *as seen on screen*: 0 right, 90 up, -90
    down. `y` is subtracted rather than added because image coordinates grow
    downward -- see the module docstring.
    """
    rad = math.radians(bearing_deg)
    return (origin[0] + length * math.cos(rad), origin[1] - length * math.sin(rad))


def _require_angle(name: str, value: float) -> None:
    """Refuse an angle `joint_angle` could not return, so a fixture cannot lie.

    `joint_angle` folds its result into [0, 180]. Asking for 200 degrees would
    build a figure that measures 160, and the test would then be asserting
    against a number the fixture never produced.
    """
    if not math.isfinite(value) or not 0.0 <= value <= 180.0:
        raise ValueError(
            f"{name} must be a finite angle in [0, 180] degrees, got {value!r}. "
            "joint_angle folds its result into that range, so anything outside it "
            "cannot be measured back."
        )


def make_person(
    *,
    person_id: int = 0,
    hip_angle_deg: float = 170.0,
    shoulder_angle_deg: float = 20.0,
    knee_angle_deg: float = 175.0,
    visible_sides: Sequence[str] = ("left", "right"),
    visible_conf: float = 0.9,
    hidden_conf: float = 0.0,
    detection_confidence: float = 0.9,
) -> PersonObservation:
    """A stick figure whose three measured joint angles are the ones requested.

    Both sides of the body are built with identical angles, so a rule that reads
    the left chain and one that reads the right see the same number.

    Args:
        person_id: Copied through to `PersonObservation.person_id`.
        hip_angle_deg: shoulder-hip-knee, the chain `sport_list['bending']`
            measures and the one the FRONT_BEND rule threshold reads. The
            default 170 is upright; below 130 is a bend.
        shoulder_angle_deg: hip-shoulder-elbow, `sport_list['armsUp']`. The
            default 20 is an arm hanging beside the torso; the legacy rule
            latches below 30.
        knee_angle_deg: hip-knee-ankle, the "is this person standing up" gate at
            aiModule.py line 322, which requires more than 160. The default 175
            is a straight leg.
        visible_sides: Which sides the model found. Each of `"left"` and
            `"right"` not listed has all eight of its keypoints replaced by
            YOLO's `(0, 0)` sentinel -- which is what makes the one-sided
            person, the case that halved every angle in the original,
            reproducible. The midline nose is never hidden.
        visible_conf: Per-keypoint score for visible keypoints. Above the
            legacy 0.6 gate by default.
        hidden_conf: Per-keypoint score for a hidden side. 0.0 by default, as
            YOLO reports. Raise it to build the nastier case -- a confidence
            gate that passes while the coordinates are still the sentinel --
            which is what a rule that trusts confidence alone gets wrong.
        detection_confidence: Copied through; the confidence of the person box.

    Raises:
        ValueError: If an angle is outside [0, 180], or `visible_sides` holds
            anything but `"left"` and `"right"`.
    """
    _require_angle("hip_angle_deg", hip_angle_deg)
    _require_angle("shoulder_angle_deg", shoulder_angle_deg)
    _require_angle("knee_angle_deg", knee_angle_deg)

    sides = tuple(visible_sides)
    unknown = sorted(set(sides) - {"left", "right"})
    if unknown:
        raise ValueError(
            f"visible_sides may only contain 'left' and 'right', got {unknown}. "
            "A misspelled side would silently hide a limb the test meant to show."
        )

    points: list[Point] = [MISSING_POINT] * KEYPOINT_COUNT

    for side_sign, joints in (
        (+1.0, (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE, LEFT_SHOULDER, LEFT_ELBOW,
                LEFT_WRIST, LEFT_EAR, LEFT_EYE)),
        (-1.0, (RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE, RIGHT_SHOULDER, RIGHT_ELBOW,
                RIGHT_WRIST, RIGHT_EAR, RIGHT_EYE)),
    ):
        hip_idx, knee_idx, ankle_idx, shoulder_idx, elbow_idx, wrist_idx, ear_idx, eye_idx = joints

        hip = (HIP_X + side_sign * SIDE_SEPARATION_PX / 2.0, HIP_Y)

        # Leg: planted straight down from the hip, then the shin swung off the
        # knee. `knee -> hip` points back up the thigh, at -90 + 180.
        thigh_bearing = -90.0
        knee = _place(hip, thigh_bearing, THIGH_PX)
        shin_bearing = (thigh_bearing + 180.0) - knee_angle_deg
        ankle = _place(knee, shin_bearing, SHIN_PX)

        # Torso: rotates about the hip, so its bearing carries the hip angle.
        torso_bearing = -90.0 + hip_angle_deg
        shoulder = _place(hip, torso_bearing, TORSO_PX)

        # Arm: hangs off the shoulder, measured from the direction back down the
        # torso, so the hip-shoulder-elbow angle is the requested one whatever
        # the torso is doing. The forearm continues straight.
        upper_arm_bearing = (torso_bearing + 180.0) + shoulder_angle_deg
        elbow = _place(shoulder, upper_arm_bearing, UPPER_ARM_PX)
        wrist = _place(elbow, upper_arm_bearing, FOREARM_PX)

        # Head: on the hip->shoulder ray extended, so ear-hip-knee reads the
        # same angle as shoulder-hip-knee.
        ear = _place(hip, torso_bearing, TORSO_PX + EAR_RISE_PX)
        eye = _place(hip, torso_bearing, TORSO_PX + EYE_RISE_PX)

        points[hip_idx] = hip
        points[knee_idx] = knee
        points[ankle_idx] = ankle
        points[shoulder_idx] = shoulder
        points[elbow_idx] = elbow
        points[wrist_idx] = wrist
        points[ear_idx] = ear
        points[eye_idx] = eye

    # The nose is the midline: halfway between where the two sides put it, so it
    # survives either side being hidden.
    nose_left = _place(
        (HIP_X + SIDE_SEPARATION_PX / 2.0, HIP_Y), -90.0 + hip_angle_deg, TORSO_PX + NOSE_RISE_PX
    )
    nose_right = _place(
        (HIP_X - SIDE_SEPARATION_PX / 2.0, HIP_Y), -90.0 + hip_angle_deg, TORSO_PX + NOSE_RISE_PX
    )
    points[NOSE] = ((nose_left[0] + nose_right[0]) / 2.0, (nose_left[1] + nose_right[1]) / 2.0)

    conf = [visible_conf] * KEYPOINT_COUNT

    # Hide the sides the model did not see: coordinates AND confidence, exactly
    # as YOLO reports a keypoint it never found.
    for side, indices in (("left", LEFT_SIDE_INDICES), ("right", RIGHT_SIDE_INDICES)):
        if side in sides:
            continue
        for index in indices:
            points[index] = MISSING_POINT
            conf[index] = hidden_conf

    return PersonObservation(
        person_id=person_id,
        keypoints_xy=tuple(points),
        keypoint_conf=tuple(conf),
        detection_confidence=detection_confidence,
    )


def make_object_detection(
    label: str,
    conf: float,
    box: tuple[float, float, float, float] = (0.0, 0.0, 10.0, 10.0),
) -> ObjectDetection:
    """One PPE-model box. `label` is a raw model class name: `no-helmet`,
    `no-jacket` or `fall` -- the strings `aiModule.py` compares at lines 416,
    426 and 434, not the engine's event names."""
    return ObjectDetection(label=label, confidence=conf, box=box)


def frame_sequence(n: int, *, start_ms: int = 0, step_ms: int = 100) -> list[int]:
    """`n` frame timestamps in milliseconds, `step_ms` apart.

    The default 100 ms is ten frames a second, the rate the original ran at.
    Timestamps rather than images because every rule under test takes a clock
    reading, never a picture.
    """
    if n < 0:
        raise ValueError(f"n must not be negative, got {n}")
    return [start_ms + i * step_ms for i in range(n)]


def describe(person: PersonObservation, indices: Iterable[int]) -> str:
    """`'left_hip=(320.0, 400.0), left_knee=...'`, for failure messages."""
    return ", ".join(f"{KEYPOINT_NAMES[i]}={person.keypoints_xy[i]}" for i in indices)
