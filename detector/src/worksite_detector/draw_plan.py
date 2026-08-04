"""What the pose overlay draws, decided as arithmetic and returned as instructions.

``aiModule.py`` lines 91-143 take these decisions *inside* a subclass of ultralytics'
``Annotator``, so reading ``if conf < 0.5: continue`` costs an ``import ultralytics``
and, through it, torch -- about 2 GB, and the end of the seconds-long feedback loop
this package is built around. None of the decisions needs an image, a frame buffer or
cv2: the confidence gates, the coordinate rules, the two filters, the one-based
skeleton offset and the size scaling are all comparisons over plain numbers. They live
here and come back as ``CircleOp`` and ``LineOp`` values. ``annotate.py``, on the far
side of the boundary ``tests/test_architecture.py`` enforces, is then a loop that hands
each instruction to ``cv2.circle`` or ``cv2.line`` with no branch left in it worth
testing.

The same split is why the float-to-int truncation and the colour lookup happen here
rather than there. Keypoints arrive as floats, or as tensor scalars that cv2 rejects
outright, and every conversion left in the drawing loop is a branch this module exists
to remove.

**The wrong question, and the right one.** The original decided whether to draw a
keypoint with ``x % shape[1] != 0 and y % shape[0] != 0`` (line 108). That asks *is
this point on or beyond an edge?*. The question it was written to answer is *is this
YOLO's missing-keypoint marker?* -- the model writes the exact pair ``(0, 0)`` for a
joint it never found, and a dot in the frame's top-left corner for every unseen joint
is how an overlay lies about what was detected. The two questions have different
answers, and the gap between them was the defect: a keypoint genuinely detected at the
top edge of the frame, or at any coordinate that happened to be an exact multiple of
the frame's width or height, was thrown away as if it had never been found.

So the test here is ``x == 0.0 and y == 0.0`` and nothing else. **A future reader will
see a sentinel check in a function that is handed the frame ``shape`` and be tempted to
"simplify" it back into an edge test, or to port the modulo across as the cheaper
``x == 0 or y == 0``. Both restore the defect.** ``(100, 0)`` is a real detection on
the top edge, ``(0, 37)`` is a real detection on the left edge, and both must draw;
only the whole pair is the marker. ``shape`` survives in the signature because it is
part of the call the ultralytics ``Annotator`` makes, but this module reads it nowhere,
and that is the fix rather than an oversight.

**Negative coordinates now agree between points and limbs.** The original's limb loop
refused an endpoint below zero (129-132) while its point loop drew one -- but only
because Python's ``-5 % 640`` is 635 rather than 0, an accident of the modulo and not a
decision. A negative pixel index is not a detection that happened, and two loops
disagreeing about identical input is the kind of asymmetry that becomes a bug report
nobody can reproduce. One predicate, ``_pixel``, now answers for both.

**The clamp asymmetry is intended.** ``int(line_thickness * size_ratio)`` is 0 for any
ratio under 0.5, and 0 is not "thin" to cv2: it is the same argument slot where a
negative means "filled", so the limb simply vanishes. Thickness is therefore floored at
1. ``radius`` is deliberately *not* floored, because ``cv2.circle`` with radius 0 still
paints a legal single pixel -- a shrunken joint stays visible. Different failure modes,
different treatment.

**Configuration is validated eagerly; frame data never raises.** A malformed skeleton
pair is refused before any filter, confidence gate or coordinate test runs, so it fails
on the first frame and every frame after. Validating it lazily would surface it only on
the frames where that limb happened to be both unfiltered and confident -- an error
that appears on some frames and not others is worse than one that always appears. A
bad *keypoint*, by contrast, is skipped rather than refused: the blast radius of every
rule in this module is dots and lines on ``output_image.jpg``, nothing here reaches
Kafka, MongoDB or the dashboard, and raising out of a real-time frame loop over a
missing dot would be the larger failure.

**Three conventions, stated once.**

* ``shape`` is ``(height, width)``, the order ``Annotator.kpts`` took it in. It is
  unused; see above.
* The colour tables are indexed by the *unfiltered* index -- keypoint ``i`` in
  ``kpts``, limb ``i`` in ``skeleton``. A filter changes which ops come out, never
  what colour they carry, so two frames drawn with different filters stay comparable.
* Every circle precedes every line, because cv2 paints in sequence and the original ran
  its two loops in that order (102-114, then 116-134). Limbs are painted over joints.

**The two filters are independent.** ``show_points`` governs the circles and
``show_skeleton`` governs the limbs, matching the original's two separate loops: a limb
between two filtered-out joints still draws. A caller asking for a sparse set of joints
over a full skeleton is asking for something coherent, and coupling the filters would
deny it while making neither of them easier to reason about.
"""
from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass

#: A BGR triple, the order cv2 draws in and the order the ultralytics tables hold.
_Color = tuple[int, int, int]

#: One keypoint as the model reports it: ``(x, y)`` or ``(x, y, confidence)``.
_Row = Sequence[float]


@dataclass(frozen=True, slots=True)
class CircleOp:
    """One joint dot, ready for ``cv2.circle(im, (x, y), radius, color, -1)``.

    Frozen because it records a decision already taken; the drawing loop reads it and
    never adjusts it. ``x`` and ``y`` are builtin ints in pixels, already truncated,
    and ``radius`` is already scaled -- it may be 0, which cv2 draws as a single pixel.
    """

    x: int
    y: int
    radius: int
    color: _Color


@dataclass(frozen=True, slots=True)
class LineOp:
    """One limb, ready for ``cv2.line(im, p1, p2, color, thickness)``.

    ``p1`` and ``p2`` are builtin int pixel pairs and ``thickness`` is already scaled
    and floored at 1, so the drawing loop needs no arithmetic of its own.
    """

    p1: tuple[int, int]
    p2: tuple[int, int]
    color: _Color
    thickness: int


def keypoint_ops(
    kpts: Sequence[_Row],
    shape: tuple[int, int],
    skeleton: Sequence[Sequence[int]],
    kpt_colors: Sequence[Sequence[int]],
    limb_colors: Sequence[Sequence[int]],
    *,
    radius: int = 5,
    line_thickness: int = 2,
    size_ratio: float = 1.0,
    conf_threshold: float = 0.5,
    show_points: Collection[int] | None = None,
    show_skeleton: Collection[Sequence[int]] | None = None,
) -> list[CircleOp | LineOp]:
    """The drawing instructions for one person's pose, circles first, then limbs.

    ``kpts`` is that person's keypoint rows, each ``(x, y)`` or ``(x, y, confidence)``;
    a two-column row carries nothing to compare and is therefore never gated on
    confidence. ``skeleton`` is the ultralytics limb table, whose indices are
    **one-based** into ``kpts``. ``kpt_colors`` and ``limb_colors`` are indexed by the
    unfiltered position of the keypoint and of the limb respectively, and are copied
    into builtin int triples so the drawing loop can pass them straight to cv2.

    ``shape`` is ``(height, width)``. It is accepted, because it is part of the call
    the ultralytics ``Annotator`` makes, and read nowhere: the module docstring
    explains why using it is the defect this module removes.

    ``radius`` and ``line_thickness`` are both multiplied by ``size_ratio``, which
    scales the overlay to the frame so that a joint on a 4K frame is not a 5-pixel
    speck, and both truncate rather than round. Thickness is floored at 1 and radius is
    not; see the module docstring for why that asymmetry is deliberate.

    ``show_points`` holds keypoint *indices* and ``show_skeleton`` holds limb *pairs*,
    matching how ``sport_list[...]['concerned_key_points_idx']`` and
    ``['concerned_skeletons_idx']`` are written at the call site. ``None`` means
    unfiltered and an empty collection means nothing survives -- they are different
    answers, and testing truthiness instead of ``is None`` conflates them.

    A keypoint is skipped, silently and without affecting any other, when its
    confidence is below ``conf_threshold``, when it is YOLO's ``(0, 0)`` marker for a
    joint that was never found, when either coordinate is negative, or when either is
    not finite -- the same three unusable coordinates ``geometry.joint_angle`` refuses,
    refused here as a missing dot rather than as an exception in the frame loop. A limb
    is skipped when either of its endpoints would be.

    Raises:
        ValueError: If a skeleton pair does not hold exactly two indices, or holds one
            that is not a valid one-based index into ``kpts``. Skeleton pairs are
            configuration, and the failure they cause otherwise is silent: a 0 in a
            one-based table becomes ``kpts[-1]`` through Python's wraparound, drawing a
            plausible limb between the wrong two joints on every frame. Checked before
            anything else, so a bad table cannot hide behind a filter or a low
            confidence. Also raised if a colour table is shorter than the keypoints or
            the skeleton it must colour, which is the same class of mistake and would
            otherwise surface as a bare ``IndexError`` naming a list the caller never
            passed.
    """
    _validate_skeleton(skeleton, len(kpts))
    _validate_palettes(len(kpts), len(skeleton), len(kpt_colors), len(limb_colors))

    ops: list[CircleOp | LineOp] = []
    if len(kpts) == 0:
        # A frame with nobody in it is the common case, so it is a quiet empty list.
        # Returning here also keeps the limb loop from indexing a row that does not
        # exist; the skeleton has already been checked for everything a missing row
        # cannot decide.
        return ops

    # Resolved once per row and shared by both loops, which is what makes the points
    # and the limbs agree about the same input by construction rather than by two
    # copies of the same three comparisons drifting apart, as they did originally.
    pixels = [_pixel(row) for row in kpts]
    confident = [_is_confident(row, conf_threshold) for row in kpts]

    scaled_radius = int(radius * size_ratio)
    for index, pixel in enumerate(pixels):
        if show_points is not None and index not in show_points:
            continue
        if not confident[index] or pixel is None:
            continue
        ops.append(
            CircleOp(
                x=pixel[0],
                y=pixel[1],
                radius=scaled_radius,
                color=_color(kpt_colors[index]),
            )
        )

    # Floored at 1: int(2 * 0.4) is 0, and a zero-thickness cv2 line draws nothing.
    scaled_thickness = max(1, int(line_thickness * size_ratio))
    # Normalised to tuples so a table of lists and a filter of tuples still match; the
    # original compared the raw objects and would have silently drawn every limb.
    wanted = None if show_skeleton is None else {tuple(pair) for pair in show_skeleton}
    for index, pair in enumerate(skeleton):
        if wanted is not None and tuple(pair) not in wanted:
            continue
        first, second = pair[0] - 1, pair[1] - 1
        if not (confident[first] and confident[second]):
            # Half a limb is worse than none: a line to a keypoint the model did not
            # find lands wherever the sentinel is, dragging a limb across the overlay.
            continue
        start, end = pixels[first], pixels[second]
        if start is None or end is None:
            continue
        ops.append(
            LineOp(
                p1=start,
                p2=end,
                color=_color(limb_colors[index]),
                thickness=scaled_thickness,
            )
        )

    return ops


def _validate_skeleton(skeleton: Sequence[Sequence[int]], keypoint_count: int) -> None:
    """Refuse a limb table that cannot be read, naming the pair and the index.

    The upper bound is checked only when there is a row to check against. With no
    keypoints every index is out of range, and a person-free frame must not raise; the
    one-based rule holds regardless of the frame and is checked either way.
    """
    for position, pair in enumerate(skeleton):
        if len(pair) != 2:
            raise ValueError(
                f"skeleton[{position}] is {list(pair)}: a limb joins exactly two "
                f"keypoints, so its pair holds two indices, not {len(pair)}."
            )
        for index in pair:
            if index < 1:
                raise ValueError(
                    f"skeleton[{position}] names keypoint index {index}, but the "
                    "table is one-based and the lowest valid index is 1. Python reads "
                    f"kpts[{index} - 1] as an offset from the end of the row, so this "
                    "draws a limb between the wrong two joints on every frame instead "
                    "of failing."
                )
            if 0 < keypoint_count < index:
                raise ValueError(
                    f"skeleton[{position}] names keypoint index {index}, but this "
                    f"person has {keypoint_count} keypoints, so the highest valid "
                    f"one-based index is {keypoint_count}."
                )


def _validate_palettes(
    keypoint_count: int, limb_count: int, kpt_color_count: int, limb_color_count: int
) -> None:
    """Refuse colour tables too short for what they must colour.

    Checked up front for the reason the skeleton is: the tables are configuration, they
    are indexed by the unfiltered position, and a short one that a filter happens to
    keep clear of is a crash waiting for the frame that lifts the filter.
    """
    if kpt_color_count < keypoint_count:
        raise ValueError(
            f"kpt_colors has length {kpt_color_count} and kpts has length "
            f"{keypoint_count}. The table is indexed by each keypoint's position in "
            "kpts, so it needs an entry per keypoint even when a filter hides some."
        )
    if limb_color_count < limb_count:
        raise ValueError(
            f"limb_colors has length {limb_color_count} and skeleton has length "
            f"{limb_count}. The table is indexed by each limb's position in skeleton, "
            "so it needs an entry per pair even when a filter hides some."
        )


def _pixel(row: _Row) -> tuple[int, int] | None:
    """Where this keypoint draws, or None if it is not a detection that happened.

    Truncation, not rounding, matching ``int(x_coord)`` at line 113 -- and it happens
    here so that ``annotate.py`` never converts anything. The three refusals are the
    module docstring's: the exact ``(0, 0)`` marker, a negative pixel index, and a
    coordinate that is not finite. All three are tested on the reported value rather
    than on the truncated one, because the marker is bit-exact -- the model writes
    literal ``0.0`` -- and a tolerance of half a pixel either way would start calling
    genuine corner detections sentinels and genuine off-frame ones on-frame.
    """
    x, y = float(row[0]), float(row[1])
    if not (math.isfinite(x) and math.isfinite(y)):
        # int(nan) and int(inf) raise, and the traceback would name this module rather
        # than the model that produced the row. A dot is not worth a dead frame loop.
        return None
    if x == 0.0 and y == 0.0:
        return None
    if x < 0.0 or y < 0.0:
        return None
    return int(x), int(y)


def _is_confident(row: _Row, threshold: float) -> bool:
    """Whether this row clears the confidence gate, or carries no confidence at all.

    Strictly below the threshold is dropped, exactly as ``if conf < 0.5`` had it: the
    threshold value itself draws, and a ``<=`` would blank the joints of every person
    the model is exactly half sure about. A row without a third column is not "zero
    confidence", it is a pose format that reports none, so it is drawn unconditionally.
    """
    if len(row) < 3:
        return True
    return float(row[2]) >= threshold


def _color(entry: Sequence[int]) -> _Color:
    """One palette entry as a builtin int triple.

    The caller's table may be a numpy row of uint8, which cv2 rejects in the colour
    slot; converting here is what keeps the drawing loop free of the comprehension
    ultralytics writes at each of its own call sites.
    """
    return int(entry[0]), int(entry[1]), int(entry[2])
