"""Unit tests for `worksite_detector.draw_plan.keypoint_ops` -- every decision the pose
overlay makes, lifted out of the drawing that used to hide it.

`aiModule.py` lines 91-143 bury those decisions inside a subclass of ultralytics'
`Annotator`. Reading `if conf < 0.5: continue` therefore costs an `import ultralytics`,
and through it torch -- about 2 GB, and the end of the seconds-long feedback loop this
package is built around. `tests/test_architecture.py` keeps `annotate.py` on the far side
of that boundary for exactly this reason.

None of those decisions needs an image, a frame buffer or cv2. The confidence skips (lines
111-112 and 127-128), the edge rule (108, 129-132), the negative-coordinate rejection
(129-132), the point and skeleton filters (103-105, 119-121), the one-based skeleton offset
(122-123) and the radius/thickness scaling (114, 134) are arithmetic over plain lists. They
live here and come back as `CircleOp`/`LineOp` instructions. What stays in `annotate.py` is
the loop that hands each instruction to `cv2.circle` or `cv2.line` -- about thirty lines
with no branch left worth testing.

**The behaviour change, and the reasoning behind it.** The original decided whether to draw
a point with `x % shape[1] != 0 and y % shape[0] != 0` (line 108). That asks "is this point
on or beyond an edge?". The question it *meant* to ask is "is this YOLO's missing-keypoint
marker?". They are different questions, and the gap between them is the defect: a keypoint
genuinely detected at the top edge of the frame was silently dropped as if it had never
been found. The marker is the exact pair `(0, 0)`, so that -- and only that -- is what gets
skipped. `(100, 0)` is a real detection on the top edge, `(0, 37)` is a real detection on
the left edge, and both draw.

The same correction runs the other way for negatives. The original drew a *point* at a
negative coordinate only because Python's `-5 % 640` is 635 rather than 0 -- an accident of
the modulo, not a decision -- while its limb loop refused negative endpoints outright
(129-132). A negative pixel coordinate is not a detection that happened, and points and
limbs disagreeing about the same input is the kind of asymmetry that becomes a bug report
nobody can reproduce. Both skip now.

Every one of those changes is visual only: the blast radius is dots and lines on
output_image.jpg, and nothing reaches Kafka, MongoDB or the dashboard differently.

**Two conventions, stated once.**
- `shape` is `(height, width)`, the order `Annotator.kpts` took it in: `shape[1]` is the
  width. Every test below that cares says so at the call site.
- The colour tables are indexed by the *unfiltered* index -- keypoint `i` in `kpts`, limb
  `i` in `skeleton`. A filter changes which ops come out, never what colour they carry: a
  filtered view that recoloured the keypoints it kept would be worse than useless to
  anyone comparing two frames.

**Deliberately left unpinned, so the omissions read as decisions:**
- Whether `show_points` also suppresses *limbs*. In the original the point filter governed
  the circle loop alone (103-105), so a limb between two filtered-out joints still drew.
  Nothing here demands either behaviour; the limb tests isolate themselves from it.
- Whether a skeleton pair that `show_skeleton` filters out, or that is dropped for low
  confidence, is still validated. `test_malformed_skeleton_index_raises` passes neither a
  filter nor a weak keypoint, so an implementation may validate eagerly or lazily.
"""
from __future__ import annotations

from typing import Any

import pytest
from worksite_detector.draw_plan import CircleOp, LineOp, keypoint_ops

# (height, width). 640 is the width, so `shape[1] == 640` matches the original's indexing.
SHAPE = (480, 640)


def _palette(base: int, count: int = 8) -> tuple[tuple[int, int, int], ...]:
    """`count` distinct BGR triples, none of them a plausible hardcoded default.

    Every component stays inside 0-255 so the tables are indistinguishable from real
    ultralytics colours, and no entry of one table can collide with an entry of the other.
    """
    return tuple((base + i, base + 10 * i + 1, base + 20 * i + 2) for i in range(count))


KPT_COLORS = _palette(31)
LIMB_COLORS = _palette(97)

# The documented defaults. Any test that does not pass them is asserting against them.
DEFAULT_RADIUS = 5
DEFAULT_THICKNESS = 2

# Confidence for a keypoint that is not itself under test: comfortably over the 0.5 gate,
# and off 1.0 so a stray default cannot masquerade as a real reading.
CONF = 0.9

Row = tuple[float, ...]


def _ops(kpts: list[Row], *, shape: tuple[int, int] = SHAPE, skeleton: Any = (), **kwargs: Any):
    """`keypoint_ops` with this file's palettes and an empty skeleton by default."""
    return keypoint_ops(kpts, shape, list(skeleton), KPT_COLORS, LIMB_COLORS, **kwargs)


def _circles(ops: list[Any]) -> list[CircleOp]:
    return [op for op in ops if isinstance(op, CircleOp)]


def _lines(ops: list[Any]) -> list[LineOp]:
    return [op for op in ops if isinstance(op, LineOp)]


# --------------------------------------------------------------------------
# Confidence
# --------------------------------------------------------------------------


def test_low_confidence_keypoint_skipped() -> None:
    # Pins aiModule.py 111-112 exactly: the comparison is `conf < threshold`, so 0.5 draws
    # and only what is strictly below it is dropped. A `<=` would blank the joints of every
    # person the model is exactly half sure about.
    below = _ops([(10.0, 20.0, 0.499)])
    at_boundary = _ops([(10.0, 20.0, 0.5)])

    assert below == []
    assert at_boundary == [
        CircleOp(x=10, y=20, radius=DEFAULT_RADIUS, color=KPT_COLORS[0])
    ]


def test_two_dim_keypoints_bypass_confidence_filter() -> None:
    # Pins `if len(k) == 3` (line 109): a two-column row carries no confidence to compare,
    # so it is drawn unconditionally. An implementation that reads `k[2]` blindly raises
    # IndexError here, and one that treats a missing confidence as 0.0 draws nothing at all.
    kpts = [(10.0, 20.0), (30.0, 40.0)]

    default_gate = _ops(kpts)
    impossible_gate = _ops(kpts, conf_threshold=0.99)

    expected = [
        CircleOp(x=10, y=20, radius=DEFAULT_RADIUS, color=KPT_COLORS[0]),
        CircleOp(x=30, y=40, radius=DEFAULT_RADIUS, color=KPT_COLORS[1]),
    ]
    assert default_gate == expected
    assert impossible_gate == expected


def test_line_requires_both_endpoints_confident() -> None:
    # Pins lines 124-128: `conf1 < 0.5 or conf2 < 0.5` drops the limb. Half a limb is worse
    # than none -- a line to a keypoint the model did not find lands wherever the sentinel
    # is. The confident endpoint still gets its own circle; only the limb goes.
    skeleton = [[1, 2]]

    first_weak = _ops([(10.0, 20.0, 0.4), (30.0, 40.0, 0.9)], skeleton=skeleton)
    second_weak = _ops([(10.0, 20.0, 0.9), (30.0, 40.0, 0.4)], skeleton=skeleton)
    both_strong = _ops([(10.0, 20.0, 0.9), (30.0, 40.0, 0.9)], skeleton=skeleton)

    assert _lines(first_weak) == []
    assert _lines(second_weak) == []
    assert _lines(both_strong) == [
        LineOp(p1=(10, 20), p2=(30, 40), color=LIMB_COLORS[0], thickness=DEFAULT_THICKNESS)
    ]


def test_conf_threshold_is_configurable() -> None:
    # NOT ON THE ORIGINAL TEST LIST -- added because an implementation that hardcodes 0.5
    # passes every other confidence test in this file, and the parameter would then be a
    # decorative default. Both loops must read it: points (line 111) and limbs (line 127).
    below = _ops([(10.0, 20.0, 0.79)], conf_threshold=0.8)
    at_boundary = _ops([(10.0, 20.0, 0.8)], conf_threshold=0.8)
    weak_limb = _ops(
        [(10.0, 20.0, 0.79), (30.0, 40.0, 0.9)], skeleton=[[1, 2]], conf_threshold=0.8
    )

    assert below == []
    assert at_boundary == [CircleOp(x=10, y=20, radius=DEFAULT_RADIUS, color=KPT_COLORS[0])]
    assert _lines(weak_limb) == []


# --------------------------------------------------------------------------
# Coordinates: the sentinel, the edges and the negatives
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentinel",
    [(0.0, 0.0, CONF), (0.0, 0.0)],
    ids=["with_confidence", "two_column"],
)
def test_zero_coordinate_sentinel_skipped(sentinel: Row) -> None:
    # The behaviour the original's modulo test (line 108) was reaching for, asked as the
    # question it meant: is this row YOLO's missing-keypoint marker? The marker is the exact
    # pair (0, 0) -- the model writes it for a joint it never found -- and a dot in the
    # frame's top-left corner for every unseen joint is how the overlay lies about what was
    # detected. Exactly (0, 0) skips; a single zero coordinate does not, because a real
    # detection can sit on the top or the left edge (see the two tests below).
    #
    # The high confidence on the sentinel row is deliberate: the skip has to come from the
    # coordinates, not from the confidence gate.
    ops = _ops([sentinel, (10.0, 20.0, CONF)])

    assert ops == [CircleOp(x=10, y=20, radius=DEFAULT_RADIUS, color=KPT_COLORS[1])]


@pytest.mark.parametrize(
    ("point", "shape", "why"),
    [
        ((100.0, 0.0), (50, 100), "x sits exactly on the right edge of a 100-wide frame"),
        ((40.0, 50.0), (50, 100), "y sits exactly on the bottom edge of a 50-high frame"),
        ((200.0, 30.0), (50, 100), "x is twice the width, off-frame but not a sentinel"),
    ],
    ids=["right_edge", "bottom_edge", "twice_the_width"],
)
def test_point_on_an_edge_is_still_drawn(
    point: tuple[float, float], shape: tuple[int, int], why: str
) -> None:
    # A LATENT DEFECT BEING FIXED, not a behaviour being preserved. aiModule.py line 108
    # drew a point only when `x % shape[1] != 0 and y % shape[0] != 0`, which answers "is
    # this on or beyond an edge?" -- not the "is this the missing-keypoint marker?" it was
    # written to answer. Every keypoint whose coordinate happened to be an exact multiple of
    # the frame's width or height was thrown away as if the model had never found it.
    # The consequence is visual only: a dot missing from output_image.jpg, and nothing that
    # reaches Kafka, MongoDB or the dashboard.
    ops = _ops([(point[0], point[1], CONF)], shape=shape)

    assert ops == [
        CircleOp(
            x=int(point[0]), y=int(point[1]), radius=DEFAULT_RADIUS, color=KPT_COLORS[0]
        )
    ], f"dropped a keypoint because {why}; that is the modulo defect at aiModule.py line 108"


@pytest.mark.parametrize(
    ("point", "why"),
    [
        ((0.0, 37.0), "a real detection on the left edge: x == 0 beside a real y"),
        ((37.0, 0.0), "a real detection on the top edge: y == 0 beside a real x"),
    ],
    ids=["left_edge", "top_edge"],
)
def test_half_sentinel_is_a_real_detection_and_is_drawn(
    point: tuple[float, float], why: str
) -> None:
    # NOT ON THE ORIGINAL TEST LIST -- a second visual-only fix that follows from the same
    # correction as the edge rule above, and is wanted. Only the whole pair (0, 0) is YOLO's
    # marker; one zero coordinate beside a real one is a joint the model genuinely located,
    # against the left or top edge of the frame. The original's `and` dropped both of these,
    # and a rewrite that ports the modulo across as `x == 0 or y == 0` keeps dropping them --
    # the sentinel test would still be answering the wrong question, just faster.
    ops = _ops([(point[0], point[1], CONF)])

    assert ops == [
        CircleOp(
            x=int(point[0]), y=int(point[1]), radius=DEFAULT_RADIUS, color=KPT_COLORS[0]
        )
    ], f"dropped {point}, which is {why}; only the exact pair (0, 0) is the marker"


@pytest.mark.parametrize(
    "negative",
    [(-5.0, 20.0, CONF), (10.0, -20.0, CONF), (-5.0, -20.0, CONF)],
    ids=["x", "y", "both"],
)
def test_negative_coordinates_skip_point(negative: Row) -> None:
    # NOT ON THE ORIGINAL TEST LIST, and a behaviour change. The original drew negative
    # points, but only because Python's `-5 % 640` is 635 rather than 0: an accident of the
    # modulo, not a decision, and its limb loop refused those very coordinates (129-132). A
    # negative pixel index is not a detection that happened, and points and limbs
    # disagreeing about identical input is an unreproducible bug report waiting to be filed.
    # The second row is real, so the skip cannot pass vacuously.
    ops = _ops([negative, (10.0, 20.0, CONF)])

    assert ops == [CircleOp(x=10, y=20, radius=DEFAULT_RADIUS, color=KPT_COLORS[1])]


@pytest.mark.parametrize(
    "kpts",
    [
        [(-5.0, 20.0, CONF), (30.0, 40.0, CONF)],
        [(10.0, -20.0, CONF), (30.0, 40.0, CONF)],
        [(10.0, 20.0, CONF), (-30.0, 40.0, CONF)],
        [(10.0, 20.0, CONF), (30.0, -40.0, CONF)],
    ],
    ids=["p1_x", "p1_y", "p2_x", "p2_y"],
)
def test_negative_coordinates_skip_line(kpts: list[Row]) -> None:
    # Pins lines 129-132: `pos[0] < 0 or pos[1] < 0` refuses the limb. A negative pixel
    # index is off-frame in a direction cv2 will happily draw towards, dragging a limb
    # across the whole overlay from a keypoint that was never really there. Every one of
    # the four coordinates is checked, because three-of-four is the shape this bug takes.
    ops = _ops(kpts, skeleton=[[1, 2]])

    assert _lines(ops) == []


@pytest.mark.parametrize(
    "kpts",
    [
        [(0.0, 0.0, CONF), (30.0, 40.0, CONF)],
        [(10.0, 20.0, CONF), (0.0, 0.0, CONF)],
    ],
    ids=["p1_sentinel", "p2_sentinel"],
)
def test_sentinel_endpoint_skips_line(kpts: list[Row]) -> None:
    # NOT ON THE ORIGINAL TEST LIST -- the sentinel rule's other half. If one end of a limb
    # is the missing-keypoint marker then the limb's position is unknown, and drawing it
    # connects a real joint to the frame's top-left corner: a line straight across the
    # overlay to a joint that was never detected. Confidence is high on both rows on
    # purpose, so the drop is attributable to the coordinates alone.
    ops = _ops(kpts, skeleton=[[1, 2]])

    assert _lines(ops) == []


# --------------------------------------------------------------------------
# Skeleton
# --------------------------------------------------------------------------


def test_skeleton_indices_are_one_based() -> None:
    # Pins `sk[0] - 1` / `sk[1] - 1` (lines 122-123). The ultralytics skeleton table is
    # one-based; reading it zero-based draws every limb one joint down the body, which is
    # an overlay that looks almost right. Three distinct points, so an off-by-one shows.
    kpts = [(10.0, 20.0, CONF), (30.0, 40.0, CONF), (50.0, 60.0, CONF)]

    ops = _ops(kpts, skeleton=[[1, 2]])

    assert _lines(ops) == [
        LineOp(p1=(10, 20), p2=(30, 40), color=LIMB_COLORS[0], thickness=DEFAULT_THICKNESS)
    ]


@pytest.mark.parametrize(
    ("skeleton", "offender"),
    [
        ([[0, 1]], "0"),
        ([[1, 4]], "4"),
        ([[-1, 2]], "-1"),
    ],
    ids=["zero_wraps_to_last", "past_the_end", "negative_wraps"],
)
def test_malformed_skeleton_index_raises(skeleton: list[list[int]], offender: str) -> None:
    # NOT ON THE ORIGINAL TEST LIST, and the failure mode is the reason it is here. A
    # one-based table with a 0 in it becomes `kpts[-1]` through Python's wraparound, so the
    # original drew a limb between the wrong two joints -- silently, plausibly, on every
    # frame. That is precisely the defect class this rewrite exists to end. Skeleton pairs
    # are configuration, so a bad one must fail where it is declared rather than paint a
    # lie. An index past the end raised a bare IndexError before, which names a list the
    # caller never passed; the message has to name the index they did pass.
    kpts = [(10.0, 20.0, CONF), (30.0, 40.0, CONF), (50.0, 60.0, CONF)]

    with pytest.raises(ValueError) as excinfo:
        _ops(kpts, skeleton=skeleton)

    assert offender in str(excinfo.value), (
        f"raised ValueError but the message was {str(excinfo.value)!r}. It must name the "
        f"offending index {offender} -- a real skeleton table is a dozen pairs long and "
        f"'invalid skeleton' does not say which one to fix."
    )


def test_show_skeleton_filter_applies() -> None:
    # Pins lines 119-121: `if sk not in show_skeleton: continue`. The filter holds the
    # limb *pairs* themselves, not their positions -- that is how the call site would pass
    # `sport_list[...]['concerned_skeletons_idx']` (aiModule.py 27, 35, 43). The surviving
    # limb keeps LIMB_COLORS[1], its index in the full skeleton, not [0], its index in the
    # filtered result. `None` means unfiltered; an empty filter means empty, and an
    # implementation testing `if show_skeleton:` instead of `is not None` conflates them.
    kpts = [
        (10.0, 20.0, CONF),
        (30.0, 40.0, CONF),
        (50.0, 60.0, CONF),
        (70.0, 80.0, CONF),
    ]
    skeleton = [[1, 2], [2, 3], [3, 4]]

    filtered = _ops(kpts, skeleton=skeleton, show_skeleton=[[2, 3]])
    unfiltered = _ops(kpts, skeleton=skeleton, show_skeleton=None)
    empty = _ops(kpts, skeleton=skeleton, show_skeleton=[])

    assert _lines(filtered) == [
        LineOp(p1=(30, 40), p2=(50, 60), color=LIMB_COLORS[1], thickness=DEFAULT_THICKNESS)
    ]
    assert [op.p1 for op in _lines(unfiltered)] == [(10, 20), (30, 40), (50, 60)]
    assert _lines(empty) == []


# --------------------------------------------------------------------------
# Point filter
# --------------------------------------------------------------------------


def test_show_points_filter_applies() -> None:
    # Pins lines 103-105: `if i not in show_points: continue`. Kept keypoint 2 must carry
    # KPT_COLORS[2] -- its index in `kpts` -- not KPT_COLORS[1], its position in the output;
    # re-indexing the palette after a filter recolours the whole figure. `None` is
    # unfiltered and `[]` is nothing, for the same reason as the skeleton filter.
    kpts = [
        (10.0, 20.0, CONF),
        (30.0, 40.0, CONF),
        (50.0, 60.0, CONF),
        (70.0, 80.0, CONF),
    ]

    filtered = _ops(kpts, show_points=[0, 2])
    unfiltered = _ops(kpts, show_points=None)
    empty = _ops(kpts, show_points=[])

    assert filtered == [
        CircleOp(x=10, y=20, radius=DEFAULT_RADIUS, color=KPT_COLORS[0]),
        CircleOp(x=50, y=60, radius=DEFAULT_RADIUS, color=KPT_COLORS[2]),
    ]
    assert [(op.x, op.y) for op in unfiltered] == [(10, 20), (30, 40), (50, 60), (70, 80)]
    assert empty == []


# --------------------------------------------------------------------------
# Scaling
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("radius", "size_ratio", "expected"),
    [
        (5, 1.0, 5),
        (5, 2.0, 10),
        (5, 1.4, 7),
        (5, 1.9, 9),
        (3, 2.0, 6),
    ],
    ids=["identity", "double", "one_point_four", "truncates_not_rounds", "custom_radius"],
)
def test_radius_scales_with_size_ratio(radius: int, size_ratio: float, expected: int) -> None:
    # Pins `int(radius * plot_size_redio)` (line 114). `plot_size_redio` scales the whole
    # overlay to the frame, so a joint dot on a 4K frame is not a 5-pixel speck. The 1.9
    # case is the one that matters twice over: 5 * 1.9 is 9.5, which truncates to 9 and
    # rounds to 10, so it forbids swapping int() for round(). The custom radius forbids
    # hardcoding 5.
    ops = _ops([(10.0, 20.0, CONF)], radius=radius, size_ratio=size_ratio)

    assert ops == [CircleOp(x=10, y=20, radius=expected, color=KPT_COLORS[0])]


@pytest.mark.parametrize(
    ("line_thickness", "size_ratio", "expected"),
    [
        (2, 0.1, 1),
        (2, 0.4, 1),
        (2, 0.6, 1),
        (2, 2.0, 4),
        (3, 1.0, 3),
    ],
    ids=["clamped", "clamped_just_under", "lands_on_one", "not_clamped", "custom_thickness"],
)
def test_thickness_never_below_one(
    line_thickness: int, size_ratio: float, expected: int
) -> None:
    # `int(line_thickness * plot_size_redio)` (line 134) is 0 for any ratio under 0.5, and
    # cv2 mishandles a zero thickness -- it is the same argument slot where a negative means
    # "filled", so 0 is not "thin", it is undefined. Clamping at 1 is the only safe floor.
    # The unclamped rows are here so the clamp cannot be a constant 1.
    #
    # THE ASYMMETRY WITH `radius` IS INTENDED and is not an oversight: `cv2.circle` with
    # radius 0 draws a legal single pixel, so a shrunken keypoint stays visible, whereas
    # `cv2.line` with thickness 0 draws nothing at all and the limb disappears. Different
    # failure modes, different treatment -- radius is deliberately left unclamped.
    ops = _ops(
        [(10.0, 20.0, CONF), (30.0, 40.0, CONF)],
        skeleton=[[1, 2]],
        line_thickness=line_thickness,
        size_ratio=size_ratio,
    )

    assert _lines(ops) == [
        LineOp(p1=(10, 20), p2=(30, 40), color=LIMB_COLORS[0], thickness=expected)
    ]


# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------


def test_colors_come_from_the_supplied_tables() -> None:
    # The original read `self.kpt_color[i]` and `self.limb_color[i]` off the ultralytics
    # Annotator, and fell back to a global `Colors()` singleton when the pose had an
    # unexpected shape (line 106). Neither is reachable from a module that must not import
    # ultralytics, so the palette is the caller's -- and it must be read by index, not
    # replaced by a default that happens to look plausible on screen.
    kpts = [(10.0, 20.0, CONF), (30.0, 40.0, CONF), (50.0, 60.0, CONF)]

    ops = _ops(kpts, skeleton=[[1, 2], [2, 3]])

    assert [op.color for op in _circles(ops)] == [
        KPT_COLORS[0],
        KPT_COLORS[1],
        KPT_COLORS[2],
    ]
    assert [op.color for op in _lines(ops)] == [LIMB_COLORS[0], LIMB_COLORS[1]]


# --------------------------------------------------------------------------
# Degenerate input
# --------------------------------------------------------------------------


def test_empty_keypoints_produce_no_ops() -> None:
    # A frame with no person in it is the common case -- PROVENANCE.md counts 278
    # person-free frames on the real clip -- and it must be a quiet empty list, not an
    # IndexError out of a colour table lookup and not a crash in the caller's draw loop.
    assert keypoint_ops([], SHAPE, [], KPT_COLORS, LIMB_COLORS) == []


# --------------------------------------------------------------------------
# Op shape
#
# NOT ON THE ORIGINAL TEST LIST -- added because both of these are load-bearing for the
# thirty lines left in `annotate.py`, and nothing above would catch them.
# --------------------------------------------------------------------------


def test_circles_precede_lines() -> None:
    # Draw order is z-order: cv2 paints in sequence, so whichever op comes last is on top.
    # aiModule.py runs its two loops in this order -- every circle (102-114), then every
    # limb (116-134) -- so limbs are painted over joints. Reversing it is a visible change
    # to the overlay with nothing to gain, and preserving observable behaviour wherever
    # there is no reason to change it is what having a baseline is for.
    kpts = [(10.0, 20.0, CONF), (30.0, 40.0, CONF)]

    ops = _ops(kpts, skeleton=[[1, 2]])

    assert [type(op) for op in ops] == [CircleOp, CircleOp, LineOp]


def test_float_coordinates_are_truncated_to_int() -> None:
    # Pins `int(x_coord)` (line 113) and `int(kpts[..., 0])` (122-123). Keypoints arrive as
    # floats -- or as numpy scalars, which cv2 rejects outright -- and the conversion has to
    # happen here, in the pure module, or `annotate.py` grows the branch this split exists
    # to remove. Exact `type(...) is int`, because bool and numpy scalars both pass
    # isinstance checks against int.
    ops = _ops([(10.9, 20.9, CONF), (30.9, 40.9, CONF)], skeleton=[[1, 2]])

    assert [(op.x, op.y) for op in _circles(ops)] == [(10, 20), (30, 40)]
    assert [(op.p1, op.p2) for op in _lines(ops)] == [((10, 20), (30, 40))]
    assert [type(op.x) for op in _circles(ops)] == [int, int]
