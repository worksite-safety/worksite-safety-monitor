"""The angle at one skeletal joint, in degrees.

Every gesture rule in this package -- arms up, bending, front bending -- is a
threshold on a single joint angle, so this is the one place where pose keypoints
become a number a rule can compare.

It replaces ``aiModule.py::calculate_angle``, which measured the left side and
the right side of the body and returned their mean *unconditionally*, while both
call sites admitted a person with only one side visible. Standing side-on was
enough to break it: the hidden side's keypoints arrive as YOLO's ``(0, 0)``
sentinel for "not found", ``math.atan2(0, 0)`` is ``0.0`` rather than an error,
and that zero was averaged into the real measurement -- halving it before every
threshold comparison downstream. The arithmetic was never the problem; what the
function accepted was. Taking exactly one three-point chain is therefore the
fix itself: a caller physically cannot hand in two limbs to be averaged, and a
limb that was never seen has to be excluded before it reaches this code.

**Why degenerate input raises instead of returning a value.** There is no number
this function could return that a caller would notice. Every consumer is a
threshold comparison, and each degenerate input already *has* a plausible-looking
answer -- which is precisely how the original defect stayed invisible for so
long:

* A zero-length ray, i.e. the ``(0, 0)`` sentinel: ``atan2(0, 0)`` is ``0.0``,
  which sits below every ``maintaining`` threshold, so the gesture state machine
  latches and eventually publishes an event that never happened.
* A NaN coordinate: it propagates through every arithmetic step without
  complaint and comes back as a well-typed float, but ``nan < maintaining`` and
  ``nan > relaxing`` are both False, so that gesture is muted permanently.
* An infinite coordinate: ``atan2(1, inf)`` is ``0.0``, collapsing both rays onto
  one bearing and yielding a confident, wrong ``0.0``. This is the worst of the
  three -- it makes the detector cry wolf rather than go quiet.

None of the three raises anywhere else in the pipeline and none writes a log
line, so an exception here is the only way a caller learns the frame was
unusable, and the only way a bad frame is dropped instead of published. A
sentinel return -- ``None``, ``-1.0``, NaN -- would push that judgement back out
to every call site, to be forgotten at one of them.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]


def joint_angle(points: Sequence[Point]) -> float:
    """Angle at the vertex, in degrees, in [0, 180].

    ``points`` is exactly three: ``[end_a, vertex, end_b]``. The result is the
    unsigned separation of the two rays leaving the vertex, so it is unchanged by
    swapping the two ends, by where the person stands in frame and by how long
    their limbs appear -- reflex angles are folded back below 180.

    Coordinates may be any real number type, including tensor elements; they are
    converted with ``float()`` and the return is always a builtin ``float``.

    Raises:
        ValueError: If ``points`` is not exactly three ``(x, y)`` pairs, if any
            coordinate is not finite, or if either ray has zero length. See the
            module docstring for why each of these is refused rather than
            answered.
    """
    if len(points) != 3:
        raise ValueError(
            "joint_angle measures one chain of exactly three points, "
            f"[end_a, vertex, end_b], but got {len(points)}. Two limbs cannot be "
            "averaged into one angle -- call it once per joint instead."
        )

    chain: list[Point] = []
    for label, point in zip(("end_a", "vertex", "end_b"), points, strict=True):
        if len(point) == 3:
            raise ValueError(
                f"{label} has three elements. A YOLO keypoint row is "
                "(x, y, confidence); drop the confidence column and pass an (x, y) "
                "pair, or the third element is silently read as a coordinate."
            )
        if len(point) != 2:
            raise ValueError(f"{label} must be an (x, y) pair, but has {len(point)} elements.")

        x, y = float(point[0]), float(point[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError(
                f"{label} is ({x!r}, {y!r}); every coordinate must be finite. A NaN "
                "would mute this gesture and an infinity would fabricate one."
            )
        chain.append((x, y))

    (end_a_x, end_a_y), (vertex_x, vertex_y), (end_b_x, end_b_y) = chain
    a_dx, a_dy = end_a_x - vertex_x, end_a_y - vertex_y
    b_dx, b_dy = end_b_x - vertex_x, end_b_y - vertex_y

    for label, dx, dy in (("end_a", a_dx, a_dy), ("end_b", b_dx, b_dy)):
        # Exactly zero, not "within some epsilon". The sentinel this catches is
        # bit-exact -- YOLO writes literal 0.0 for a keypoint it did not find --
        # whereas any tolerance would be an arbitrary pixel count and would start
        # rejecting genuinely short limbs, which are ordinary far-field detections.
        if dx == 0.0 and dy == 0.0:
            raise ValueError(
                f"{label} coincides with the vertex at ({vertex_x!r}, {vertex_y!r}), so "
                "that ray has no direction and no angle exists. A keypoint YOLO did not "
                "find arrives as (0, 0); exclude the limb rather than measuring it."
            )

    # atan2(|cross|, dot) rather than acos(dot / (|a| * |b|)): acos loses
    # precision exactly where these gestures are decided, near 0 and 180 degrees,
    # where its derivative diverges and an error of 1e-16 in the cosine becomes
    # ~1e-6 degrees in the answer. This form is accurate at both ends, and because
    # the first argument is never negative the result is in [0, pi] by
    # construction -- so [0, 180] needs no clamping, and the reflex fold that
    # aiModule.py did with `360 - angle_diff` is just the abs().
    cross = a_dx * b_dy - a_dy * b_dx
    dot = a_dx * b_dx + a_dy * b_dy
    return math.degrees(math.atan2(abs(cross), dot))
