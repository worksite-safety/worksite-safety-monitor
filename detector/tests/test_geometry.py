"""Unit tests for `worksite_detector.geometry.joint_angle`.

These pin the replacement for `aiModule.py::calculate_angle` (lines 48-88) and the
defect that module exists to kill.

The legacy function computes a left-side angle and a right-side angle and returns
`(angle_left + angle_right) / 2` *unconditionally* (line 87). Both call sites --
lines 321 and 358 -- admit a person with only ONE side visible, because the
visibility gate is an `or` of two `and` chains. When someone stands side-on, the
invisible side's keypoints are YOLO's `(0, 0)` sentinels, `math.atan2(0, 0)`
returns `0.0` without complaint, and that garbage zero is averaged into the real
measurement -- halving it before every threshold comparison downstream.

`joint_angle` is structurally immune: it takes exactly one three-point chain, so a
caller physically cannot average in an invisible limb, and it raises on the
degenerate `(0, 0)` sentinel rather than returning a plausible-looking number.
"""
from __future__ import annotations

import math

import pytest
from worksite_detector.geometry import joint_angle

# Every comparison below is exact-value-with-explicit-tolerance. 1e-9 is far
# wider than the ~1e-13 that double-precision trigonometry costs us, and far
# tighter than any error that would change a gesture decision.
TOL = 1e-9

# The sweep alone gets a looser bound. It walks directions that are 0 and 180
# degrees apart, where an acos-based formula is ill-conditioned: an error of
# 1e-16 in the cosine becomes ~1e-6 degrees in the answer. That is a property of
# the algorithm, not a contract violation, and pinning 1e-9 there would quietly
# forbid a legitimate implementation. 1e-5 still catches any real mistake --
# the gesture thresholds are 30, 130, 140 and 160 degrees apart.
SWEEP_TOL = 1e-5

Point = tuple[float, float]


def _chain(
    vertex: Point,
    deg_a: float,
    deg_b: float,
    len_a: float = 1.0,
    len_b: float = 1.0,
) -> list[Point]:
    """Build `[end_a, vertex, end_b]` with the two rays leaving `vertex` at the
    given polar angles in degrees.

    The expected result is then known by construction -- it is the folded
    difference of `deg_a` and `deg_b` -- so no test has to borrow the
    implementation's own arithmetic to state what it wants.
    """

    def _end(deg: float, length: float) -> Point:
        rad = math.radians(deg)
        return (vertex[0] + length * math.cos(rad), vertex[1] + length * math.sin(rad))

    return [_end(deg_a, len_a), vertex, _end(deg_b, len_b)]


# --------------------------------------------------------------------------
# Core values
# --------------------------------------------------------------------------


def test_right_angle() -> None:
    assert joint_angle([(0.0, 1.0), (0.0, 0.0), (1.0, 0.0)]) == pytest.approx(90.0, abs=TOL)


def test_straight_line_is_180() -> None:
    # Upper bound of the contract; must land on 180.0, not 179.999... or -180.0.
    assert joint_angle([(-1.0, 0.0), (0.0, 0.0), (1.0, 0.0)]) == pytest.approx(180.0, abs=TOL)


def test_coincident_rays_is_zero() -> None:
    # Lower bound. Both rays have real length, so this is a legal input, NOT a
    # degenerate one -- it must return 0.0 rather than raise.
    assert joint_angle([(1.0, 0.0), (0.0, 0.0), (1.0, 0.0)]) == pytest.approx(0.0, abs=TOL)


# --------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------


def test_symmetric_in_endpoints() -> None:
    # The angle at a joint is a property of the joint, not of which limb the
    # caller happened to list first.
    points = _chain((0.5, -1.5), 17.0, 141.0, len_a=2.0, len_b=0.25)
    swapped = [points[2], points[1], points[0]]

    forward = joint_angle(points)
    backward = joint_angle(swapped)

    assert forward == pytest.approx(124.0, abs=TOL)
    assert backward == pytest.approx(124.0, abs=TOL)
    assert forward == pytest.approx(backward, abs=TOL)


def test_always_within_0_and_180() -> None:
    # Real sweep: 36 x 36 = 1296 direction pairs, every 10 degrees around the
    # circle, including the reflex half where `aiModule.py` lines 62-63 fold.
    step = 10
    for i in range(36):
        for j in range(36):
            deg_a, deg_b = float(i * step), float(j * step)
            result = joint_angle(_chain((0.0, 0.0), deg_a, deg_b, len_a=1.0, len_b=1.3))

            assert 0.0 <= result <= 180.0, (
                f"rays at {deg_a} and {deg_b} degrees gave {result!r}; the contract is a "
                f"folded angle in [0, 180], so the result must be clamped at both ends"
            )

            # Known by construction: the folded separation of the two directions.
            expected = abs(deg_a - deg_b)
            if expected > 180.0:
                expected = 360.0 - expected
            assert result == pytest.approx(expected, abs=SWEEP_TOL), (
                f"rays at {deg_a} and {deg_b} degrees are {expected} degrees apart"
            )


def test_reflex_angle_is_folded() -> None:
    # Pins aiModule.py lines 62-63: 170 - (-170) = 340 must come back as 20.
    assert joint_angle(_chain((0.0, 0.0), 170.0, -170.0)) == pytest.approx(20.0, abs=TOL)


def test_translation_invariant() -> None:
    # Pixel coordinates are frame-relative; where the person stands in frame must
    # not change the angle of their elbow.
    base = _chain((0.0, 0.0), 20.0, 155.0, len_a=2.0, len_b=0.5)
    moved = [(x + 1000.0, y - 37.0) for x, y in base]

    assert joint_angle(base) == pytest.approx(135.0, abs=TOL)
    assert joint_angle(moved) == pytest.approx(135.0, abs=TOL)


def test_scale_invariant() -> None:
    # Limb length must not matter: someone closer to the camera has longer limbs
    # in pixels but the same joint angles.
    base = _chain((2.0, -1.0), 12.0, 88.0, len_a=3.0, len_b=0.7)
    scaled = [(x * 7.5, y * 7.5) for x, y in base]

    assert joint_angle(base) == pytest.approx(76.0, abs=TOL)
    assert joint_angle(scaled) == pytest.approx(76.0, abs=TOL)


# --------------------------------------------------------------------------
# Degenerate input
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("points", "why"),
    [
        ([(0.0, 0.0), (0.0, 0.0), (1.0, 0.0)], "end_a sits on the vertex"),
        ([(1.0, 0.0), (0.0, 0.0), (0.0, 0.0)], "end_b sits on the vertex"),
        ([(0.0, 0.0), (0.0, 0.0), (0.0, 0.0)], "all three are YOLO's (0, 0) sentinel"),
        ([(4.0, -2.0), (4.0, -2.0), (9.0, 9.0)], "zero-length ray away from the origin"),
    ],
    ids=["end_a_on_vertex", "end_b_on_vertex", "all_sentinel", "zero_ray_off_origin"],
)
def test_degenerate_zero_length_ray_raises(points: list[Point], why: str) -> None:
    # ROOT CAUSE of the halved-angle bug: the invisible side of a side-on person
    # arrives as (0, 0) sentinels, and the old code answered with a number anyway
    # -- math.atan2(0, 0) is 0.0, no exception -- which line 87 then averaged into
    # the visible side's real angle.
    #
    # DECISION -- "zero-length" means exactly `== 0.0`, not "shorter than some
    # epsilon", and that is deliberate. The sentinel this exists to catch is
    # bit-exact: YOLO writes literal 0.0 for a keypoint it did not find, so an
    # exact comparison catches every real occurrence. Any tolerance would be an
    # arbitrary pixel count nobody can defend, and it would start rejecting real
    # measurements of genuinely short limbs. Do not "improve" this into an
    # epsilon check.
    with pytest.raises(ValueError):
        joint_angle(points)


@pytest.mark.parametrize(
    "points",
    [
        [],
        [(0.0, 0.0)],
        [(0.0, 1.0), (0.0, 0.0)],
        [(0.0, 1.0), (0.0, 0.0), (1.0, 0.0), (2.0, 0.0)],
        [(0.0, 1.0), (0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)],
    ],
    ids=["zero", "one", "two", "four", "five"],
)
def test_wrong_point_count_raises(points: list[Point]) -> None:
    # One chain, one angle. Anything else is a caller trying to hand in two limbs
    # at once, which is how the averaging bug was possible in the first place.
    with pytest.raises(ValueError):
        joint_angle(points)


@pytest.mark.parametrize(
    "points",
    [
        [(0.0, 1.0, 0.93), (0.0, 0.0), (1.0, 0.0)],
        [(0.0, 1.0), (0.0, 0.0, 0.88), (1.0, 0.0)],
        [(0.0, 1.0), (0.0, 0.0), (1.0, 0.0, 0.71)],
        [(0.0, 1.0, 0.93), (0.0, 0.0, 0.88), (1.0, 0.0, 0.71)],
    ],
    ids=["end_a_row", "vertex_row", "end_b_row", "all_three_rows"],
)
def test_keypoint_row_with_confidence_raises(points: list[tuple[float, ...]]) -> None:
    # A YOLO keypoint row is (x, y, conf) -- see aiModule.py line 67, which hand
    # slices [0] and [1] off it. The likeliest caller mistake is forgetting that
    # slice, so the failure has to teach: Python's own "too many values to unpack
    # (expected 2)" is technically a ValueError but tells the caller nothing about
    # the confidence column they left attached.
    with pytest.raises(ValueError) as excinfo:
        joint_angle(points)

    message = str(excinfo.value)
    assert any(marker in message.lower() for marker in ("conf", "third", "3rd")), (
        f"raised ValueError but the message was {message!r}. It must name the third "
        f"element -- say 'confidence' or 'third' -- so the caller learns they passed a "
        f"whole keypoint row instead of an (x, y) pair. An incidental unpacking error "
        f"does not count."
    )


@pytest.mark.parametrize(
    "value",
    [math.nan, math.inf, -math.inf],
    ids=["nan", "inf", "neg_inf"],
)
@pytest.mark.parametrize(
    "slot",
    range(6),
    ids=["end_a_x", "end_a_y", "vertex_x", "vertex_y", "end_b_x", "end_b_y"],
)
def test_non_finite_coordinate_raises(slot: int, value: float) -> None:
    # Same silent-failure class as the (0, 0) sentinel, one step further along.
    # A NaN sails through every arithmetic step without raising and comes back as
    # a float, but `0 <= nan <= 180` is False and so is `nan < maintaining` and
    # `nan > relaxing` -- so a single bad coordinate mutes the gesture forever
    # with no error anywhere. An infinity is worse: atan2(inf, 0) is a perfectly
    # plausible 90 degrees. Refuse both rather than return them.
    flat = [0.0, 1.0, 0.0, 0.0, 1.0, 0.0]  # the right-angle chain, flattened
    flat[slot] = value
    points = [(flat[0], flat[1]), (flat[2], flat[3]), (flat[4], flat[5])]

    with pytest.raises(ValueError):
        joint_angle(points)


# --------------------------------------------------------------------------
# Numeric types at the boundary
# --------------------------------------------------------------------------


@pytest.mark.parametrize("dtype_name", ["float32", "float64"])
def test_accepts_numpy_scalars(dtype_name: str) -> None:
    # Lets the call sites hand over tensor elements directly and drop the `.item()`
    # conversions at aiModule.py lines 70-85.
    np = pytest.importorskip("numpy")
    dtype = getattr(np, dtype_name)
    points = [
        (dtype(0.0), dtype(1.0)),
        (dtype(0.0), dtype(0.0)),
        (dtype(1.0), dtype(0.0)),
    ]

    result = joint_angle(points)

    assert result == pytest.approx(90.0, abs=TOL)
    assert type(result) is float, (
        f"numpy input leaked a {type(result).__name__} out of joint_angle; "
        f"the return type must not depend on the input's numeric type"
    )


def test_returns_builtin_float() -> None:
    # np.float64 subclasses float, so isinstance() would pass on a leaked numpy
    # scalar. Only an exact type check keeps json.dumps and the event DTOs honest.
    from_floats = joint_angle([(0.0, 1.0), (0.0, 0.0), (1.0, 0.0)])
    from_ints = joint_angle([(0, 1), (0, 0), (1, 0)])

    assert type(from_floats) is float, f"got {type(from_floats).__name__}"
    assert type(from_ints) is float, f"got {type(from_ints).__name__}"


# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expected", "source"),
    [
        (30.0, "sport_list['armsUp']['maintaining'], aiModule.py line 24"),
        (130.0, "sport_list['bending']['maintaining'], aiModule.py line 33"),
        (160.0, "sport_list['bending']['relaxing'] and the upright gate, line 322"),
    ],
    ids=["30_arms_up_maintaining", "130_bend_maintaining", "160_bend_relaxing"],
)
def test_threshold_values_are_degrees(expected: float, source: str) -> None:
    # A radians/degrees mix-up returns numbers that are always below every
    # `maintaining` threshold and never above any `relaxing` one, silently
    # disabling all three gestures with no error anywhere. This is the test that
    # catches it.
    points = _chain((6.0, 2.5), 12.0, 12.0 + expected, len_a=1.7, len_b=4.2)

    result = joint_angle(points)

    assert result == pytest.approx(expected, abs=TOL), (
        f"expected {expected} degrees ({source}); radians would give "
        f"{math.radians(expected):.6f}"
    )
