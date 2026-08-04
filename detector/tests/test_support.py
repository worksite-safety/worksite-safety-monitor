"""Self-tests for the fixtures in `tests/_support`.

Test code does not normally get tested. These do, because the next unit's ~29
pose tests are all of the form "a frame in which the hip angle is 120 degrees",
and every one of them is worthless if `make_person` does not actually build that
frame. A broken builder does not produce a red suite -- it produces a green one
that proves nothing, which is strictly worse than no suite at all.

So every angle the builder claims to place is measured back out through
`worksite_detector.geometry.joint_angle`, the same function the rules call. The
builder and the measurement share no code: the builder works forward from
bearings and lengths, `joint_angle` works backward from coordinates with
`atan2`, so agreement between them is evidence rather than a tautology.

The one that matters most is `test_chains_are_independent`. The three chains
share the hip, the shoulder and the knee, so a naive builder that positions each
joint to satisfy the chain in front of it will let a change to `hip_angle_deg`
drag the shoulder or knee reading with it -- and then a downstream test that
varies the bend angle is silently varying the arms-up angle too.
"""
from __future__ import annotations

import pytest

from tests._support.builders import (
    MISSING_POINT,
    ObjectDetection,
    PersonObservation,
    describe,
    frame_sequence,
    make_object_detection,
    make_person,
)
from tests._support.fakes import (
    FakeClock,
    FakeFrameSource,
    RecordingSink,
    ScriptedObjectModel,
    ScriptedPoseModel,
)
from tests._support.keypoints import (
    KEYPOINT_COUNT,
    KEYPOINT_NAMES,
    LEFT_ANKLE,
    LEFT_EAR,
    LEFT_ELBOW,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    LEFT_SIDE_INDICES,
    NOSE,
    RIGHT_ANKLE,
    RIGHT_EAR,
    RIGHT_ELBOW,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    RIGHT_SIDE_INDICES,
)
from worksite_detector.geometry import joint_angle

# The stated contract for the builder is "within half a degree", which is an
# order of magnitude tighter than any gesture threshold gap. We hold it to 1e-9
# instead, because the construction is exact trigonometry: anything above
# double-precision noise means a real mistake in the geometry, not accumulated
# error, and there is no reason to leave half a degree of room for it.
TOL = 1e-9

# The legacy per-keypoint visibility gate, aiModule.py lines 321 and 358.
VISIBILITY_GATE = 0.6

# The three chains the rules measure, per side. `joint_angle` takes
# [end_a, vertex, end_b]; the vertex is the middle entry and names the chain.
LEFT_HIP_CHAIN = (LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE)
RIGHT_HIP_CHAIN = (RIGHT_SHOULDER, RIGHT_HIP, RIGHT_KNEE)
LEFT_SHOULDER_CHAIN = (LEFT_HIP, LEFT_SHOULDER, LEFT_ELBOW)
RIGHT_SHOULDER_CHAIN = (RIGHT_HIP, RIGHT_SHOULDER, RIGHT_ELBOW)
LEFT_KNEE_CHAIN = (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE)
RIGHT_KNEE_CHAIN = (RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE)

# Which builder argument each chain is supposed to answer to.
CHAINS = {
    "hip_angle_deg": (LEFT_HIP_CHAIN, RIGHT_HIP_CHAIN),
    "shoulder_angle_deg": (LEFT_SHOULDER_CHAIN, RIGHT_SHOULDER_CHAIN),
    "knee_angle_deg": (LEFT_KNEE_CHAIN, RIGHT_KNEE_CHAIN),
}

# The builder's own defaults, restated so a test can vary one and hold the rest.
DEFAULTS = {"hip_angle_deg": 170.0, "shoulder_angle_deg": 20.0, "knee_angle_deg": 175.0}

# A builder can be right at one value and wrong everywhere else -- an off-by-a-
# sign puts every angle on the correct side at 90 and nowhere else. These four
# straddle every threshold in sport_list: 30 (armsUp maintaining), 130 (bending
# maintaining), 160 (bending relaxing and the upright gate), 140.
SWEEP = (30.0, 90.0, 130.0, 170.0)

# Every keypoint the three chains and the visibility gates touch: the union of
# the `concerned_key_points_idx` lists in sport_list, plus the ankles, which the
# upright gate at line 322 measures without ever checking their confidence.
CONCERNED = (
    LEFT_EAR,
    RIGHT_EAR,
    LEFT_SHOULDER,
    RIGHT_SHOULDER,
    LEFT_ELBOW,
    RIGHT_ELBOW,
    LEFT_HIP,
    RIGHT_HIP,
    LEFT_KNEE,
    RIGHT_KNEE,
    LEFT_ANKLE,
    RIGHT_ANKLE,
)


def _measure(person: PersonObservation, chain: tuple[int, int, int]) -> float:
    """The angle at `chain`'s middle keypoint, read out of the built figure."""
    return joint_angle([person.keypoints_xy[i] for i in chain])


def _chain_name(chain: tuple[int, int, int]) -> str:
    return "-".join(KEYPOINT_NAMES[i] for i in chain)


# --------------------------------------------------------------------------
# The three chains measure what was asked for
# --------------------------------------------------------------------------


def test_hip_chain_measures_requested_angle() -> None:
    # shoulder-hip-knee: sport_list['bending'], which is what the FRONT_BEND
    # branch actually measures (main() binds args = Args2(), sport='bending').
    person = make_person(hip_angle_deg=120.0)

    assert _measure(person, LEFT_HIP_CHAIN) == pytest.approx(120.0, abs=TOL), describe(
        person, LEFT_HIP_CHAIN
    )
    assert _measure(person, RIGHT_HIP_CHAIN) == pytest.approx(120.0, abs=TOL), describe(
        person, RIGHT_HIP_CHAIN
    )


def test_shoulder_chain_measures_requested_angle() -> None:
    # hip-shoulder-elbow: sport_list['armsUp'], lines 22-23.
    person = make_person(shoulder_angle_deg=120.0)

    assert _measure(person, LEFT_SHOULDER_CHAIN) == pytest.approx(120.0, abs=TOL), describe(
        person, LEFT_SHOULDER_CHAIN
    )
    assert _measure(person, RIGHT_SHOULDER_CHAIN) == pytest.approx(120.0, abs=TOL), describe(
        person, RIGHT_SHOULDER_CHAIN
    )


def test_knee_chain_measures_requested_angle() -> None:
    # hip-knee-ankle: the upright gate at line 322, `> 160`.
    person = make_person(knee_angle_deg=120.0)

    assert _measure(person, LEFT_KNEE_CHAIN) == pytest.approx(120.0, abs=TOL), describe(
        person, LEFT_KNEE_CHAIN
    )
    assert _measure(person, RIGHT_KNEE_CHAIN) == pytest.approx(120.0, abs=TOL), describe(
        person, RIGHT_KNEE_CHAIN
    )


@pytest.mark.parametrize("angle", SWEEP, ids=lambda a: f"{a:g}deg")
@pytest.mark.parametrize("argument", sorted(CHAINS), ids=str)
def test_every_chain_holds_across_the_range(argument: str, angle: float) -> None:
    person = make_person(**{argument: angle})

    for chain in CHAINS[argument]:
        measured = _measure(person, chain)
        assert measured == pytest.approx(angle, abs=TOL), (
            f"asked for {argument}={angle} but {_chain_name(chain)} measures {measured}. "
            f"Points: {describe(person, chain)}"
        )


def test_defaults_describe_an_upright_person_who_is_not_bending() -> None:
    # The default figure has to be the *negative* case for every rule, or half
    # the downstream tests would be asserting against an accidental positive.
    person = make_person()

    assert _measure(person, LEFT_KNEE_CHAIN) > 160.0, "the default legs must pass the upright gate"
    assert _measure(person, LEFT_HIP_CHAIN) > 160.0, "the default torso must not read as a bend"
    assert _measure(person, LEFT_SHOULDER_CHAIN) < 30.0, "the default arm must hang beside the hip"


def test_ear_chain_agrees_with_the_shoulder_chain_at_the_hip() -> None:
    # sport_list['frontbending'] measures ear-hip-knee (lines 38-39) where
    # sport_list['bending'] measures shoulder-hip-knee. The builder puts the ear
    # on the hip->shoulder ray so both read `hip_angle_deg`, and a rule that
    # picks either chain sees the same fixture.
    person = make_person(hip_angle_deg=95.0)

    assert _measure(person, (LEFT_EAR, LEFT_HIP, LEFT_KNEE)) == pytest.approx(95.0, abs=TOL)
    assert _measure(person, (RIGHT_EAR, RIGHT_HIP, RIGHT_KNEE)) == pytest.approx(95.0, abs=TOL)


# --------------------------------------------------------------------------
# THE ONE THAT MATTERS: the chains share joints but not values
# --------------------------------------------------------------------------


@pytest.mark.parametrize("angle", SWEEP, ids=lambda a: f"{a:g}deg")
@pytest.mark.parametrize("varied", sorted(CHAINS), ids=str)
def test_chains_are_independent(varied: str, angle: float) -> None:
    # Vary exactly one argument and measure all three chains. The varied one
    # must follow; the other two must sit at their defaults, unmoved.
    #
    # This is the defect a naive builder has. The hip chain ends at the shoulder
    # and the shoulder chain starts there; the hip chain ends at the knee and the
    # knee chain starts there. Place each joint to satisfy only the chain in
    # front of it and bending the hip silently re-reads as raising an arm --
    # after which a downstream test named `test_bend_below_130_latches` is
    # actually exercising two rules at once and pinning neither.
    expected = dict(DEFAULTS)
    expected[varied] = angle
    person = make_person(**{varied: angle})

    for argument, chains in CHAINS.items():
        for chain in chains:
            measured = _measure(person, chain)
            assert measured == pytest.approx(expected[argument], abs=TOL), (
                f"with {varied}={angle}, {_chain_name(chain)} measures {measured} but "
                f"{argument} is {expected[argument]}. The chains share joints; moving one "
                f"must not move another."
            )


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


def test_person_has_seventeen_keypoints_and_seventeen_confidences() -> None:
    # A short row would be an IndexError deep inside a rule, or -- worse -- a
    # chain quietly built from the wrong joints.
    person = make_person()

    assert len(person.keypoints_xy) == KEYPOINT_COUNT
    assert len(person.keypoint_conf) == KEYPOINT_COUNT
    assert all(len(point) == 2 for point in person.keypoints_xy), (
        "each keypoint must be an (x, y) pair; joint_angle rejects a whole "
        "(x, y, conf) YOLO row"
    )


def test_person_carries_its_identifiers_through() -> None:
    person = make_person(person_id=3, detection_confidence=0.42)

    assert person.person_id == 3
    assert person.detection_confidence == pytest.approx(0.42, abs=TOL)


@pytest.mark.parametrize("bad_angle", [-1.0, 180.1, 200.0, 360.0])
def test_angle_outside_the_measurable_range_is_refused(bad_angle: float) -> None:
    # joint_angle folds into [0, 180], so a figure built for 200 degrees would
    # measure 160 and the fixture would be lying about itself.
    with pytest.raises(ValueError):
        make_person(hip_angle_deg=bad_angle)


def test_misspelled_side_is_refused() -> None:
    # `visible_sides=("Left",)` would otherwise hide the whole body and the test
    # would fail somewhere unrelated.
    with pytest.raises(ValueError):
        make_person(visible_sides=("Left",))


# --------------------------------------------------------------------------
# One-sided visibility -- the case the original could not survive
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("visible", "hidden_indices", "visible_indices"),
    [
        (("left",), RIGHT_SIDE_INDICES, LEFT_SIDE_INDICES),
        (("right",), LEFT_SIDE_INDICES, RIGHT_SIDE_INDICES),
    ],
    ids=["left_only", "right_only"],
)
def test_hidden_side_is_zeroed_in_both_coordinates_and_confidence(
    visible: tuple[str, ...],
    hidden_indices: tuple[int, ...],
    visible_indices: tuple[int, ...],
) -> None:
    # This is the fixture that reproduces the original defect: a person standing
    # side-on. YOLO reports the unseen limb as (0, 0) with confidence 0, and
    # `calculate_angle` averaged the resulting `atan2(0, 0) == 0.0` into the real
    # side's measurement, halving it. Zeroing *both* is what makes the case real
    # -- coordinates alone would let a rule pass the confidence gate, and
    # confidence alone would leave a measurable limb behind.
    person = make_person(visible_sides=visible)

    for index in hidden_indices:
        assert person.keypoints_xy[index] == MISSING_POINT, (
            f"{KEYPOINT_NAMES[index]} is on the hidden side but sits at "
            f"{person.keypoints_xy[index]}; YOLO reports (0, 0) for a keypoint it "
            f"did not find"
        )
        assert person.keypoint_conf[index] == 0.0, (
            f"{KEYPOINT_NAMES[index]} is on the hidden side but has confidence "
            f"{person.keypoint_conf[index]}; it must be 0.0, or a rule that gates on "
            f"confidence alone would still admit the (0, 0) coordinates"
        )

    for index in visible_indices:
        assert person.keypoints_xy[index] != MISSING_POINT, (
            f"{KEYPOINT_NAMES[index]} is on the visible side and must keep its coordinates"
        )
        assert person.keypoint_conf[index] > VISIBILITY_GATE

    # The midline nose belongs to neither side and is still seen side-on.
    assert person.keypoints_xy[NOSE] != MISSING_POINT


def test_hidden_side_chain_is_unmeasurable() -> None:
    # The point of the fixture: the hidden chain must be something a rule cannot
    # quietly turn into a number. joint_angle refuses it; the original returned
    # 0.0 and averaged it in.
    person = make_person(visible_sides=("left",), hip_angle_deg=120.0)

    assert _measure(person, LEFT_HIP_CHAIN) == pytest.approx(120.0, abs=TOL)
    with pytest.raises(ValueError):
        _measure(person, RIGHT_HIP_CHAIN)


def test_hidden_confidence_can_be_raised_without_restoring_the_coordinates() -> None:
    # The nastier variant: a rule that gates on confidence alone passes, and
    # then measures the (0, 0) sentinel anyway.
    person = make_person(visible_sides=("left",), hidden_conf=0.95)

    for index in RIGHT_SIDE_INDICES:
        assert person.keypoint_conf[index] == pytest.approx(0.95, abs=TOL)
        assert person.keypoints_xy[index] == MISSING_POINT


def test_both_sides_visible_clears_the_confidence_gate_everywhere_it_matters() -> None:
    # The default person must not be accidentally filtered out by the 0.6 gate,
    # or every downstream "this rule fires" test would pass for the wrong reason.
    person = make_person()

    for index in CONCERNED:
        assert person.keypoint_conf[index] > VISIBILITY_GATE, (
            f"{KEYPOINT_NAMES[index]} has confidence {person.keypoint_conf[index]}, which "
            f"does not clear the {VISIBILITY_GATE} visibility gate"
        )


# --------------------------------------------------------------------------
# The smaller builders
# --------------------------------------------------------------------------


def test_make_object_detection_defaults_and_overrides() -> None:
    default = make_object_detection("no-helmet", 0.83)
    explicit = make_object_detection("fall", 0.91, box=(4.0, 5.0, 60.0, 70.0))

    assert isinstance(default, ObjectDetection)
    assert default.label == "no-helmet"
    assert default.confidence == pytest.approx(0.83, abs=TOL)
    assert default.box == (0.0, 0.0, 10.0, 10.0)
    assert explicit.label == "fall"
    assert explicit.box == (4.0, 5.0, 60.0, 70.0)


def test_frame_sequence_is_evenly_spaced_from_the_start() -> None:
    assert frame_sequence(0) == []
    assert frame_sequence(3) == [0, 100, 200]
    assert frame_sequence(3, start_ms=1_700_000_000_000, step_ms=250) == [
        1_700_000_000_000,
        1_700_000_000_250,
        1_700_000_000_500,
    ]


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


def test_fake_clock_only_moves_when_advanced() -> None:
    clock = FakeClock(1_000)

    assert clock.now() == 1_000
    assert clock.now() == 1_000, "reading the clock must not move it"

    clock.advance(250)
    assert clock.now() == 1_250

    clock.advance(0)
    assert clock.now() == 1_250

    clock.advance(180_000)  # the FALL cooldown, aiModule.py line 437
    assert clock.now() == 181_250


def test_fake_clock_refuses_to_run_backwards() -> None:
    clock = FakeClock(500)

    with pytest.raises(ValueError):
        clock.advance(-1)
    assert clock.now() == 500


def test_fake_frame_source_yields_its_frames_in_order() -> None:
    source = FakeFrameSource(["a", "b", "c"])

    assert len(source) == 3
    assert list(source) == ["a", "b", "c"]
    assert list(source) == ["a", "b", "c"], "iterating must not consume the source"


@pytest.mark.parametrize("model_type", [ScriptedPoseModel, ScriptedObjectModel])
def test_scripted_model_returns_its_script_and_records_the_frames(
    model_type: type[ScriptedPoseModel] | type[ScriptedObjectModel],
) -> None:
    model = model_type([["first"], [], ["third"]])

    assert model(10) == ["first"]
    assert model(20) == []
    assert model(30) == ["third"]
    assert model.calls == [10, 20, 30]
    assert model.call_count == 3


@pytest.mark.parametrize("model_type", [ScriptedPoseModel, ScriptedObjectModel])
def test_scripted_model_raises_when_the_script_runs_out(
    model_type: type[ScriptedPoseModel] | type[ScriptedObjectModel],
) -> None:
    # A pipeline that reads one frame twice is a bug; returning the last result
    # again would hide it.
    model = model_type([[]])
    model(1)

    with pytest.raises(AssertionError):
        model(2)


def test_recording_sink_keeps_every_write_in_order() -> None:
    sink = RecordingSink()

    assert sink.writes == []
    sink.write("first")
    sink.write("second")

    assert sink.writes == ["first", "second"]
    assert len(sink) == 2
