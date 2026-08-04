"""The pose overlay's drawing loop: instructions in, pixels out, no decisions left.

Modified from two Apache-2.0 / AGPL-3.0 sources, and isolated here so the attribution
has exactly one home:

* ``ultralytics.utils.plotting.Annotator.kpts`` -- Ultralytics YOLO, AGPL-3.0-or-later
  (https://github.com/ultralytics/ultralytics). The base class, its skeleton table and
  its two colour palettes are used as they ship; the method body below is a rewrite of
  ``kpts``, not a copy of it.
* ``yuyoujiang/Exercise-Counter-with-YOLOv8-on-NVIDIA-Jetson`` -- Apache-2.0
  (https://github.com/yuyoujiang/Exercise-Counter-with-YOLOv8-on-NVIDIA-Jetson), whose
  ``_Annotator.kpts`` added the ``show_points`` / ``show_skeleton`` filters and the
  ``plot_size_redio`` scaling. ``aiModule.py`` lines 91-143 are that code, adopted into
  this project with the gesture table it came with.

Both notices are kept because this file is where their work survives. This project as a
whole is AGPL-3.0-or-later, which both of the above permit being combined into.

**What this module isolates, and why it is this small.** It is one of the three files
``tests/test_architecture.py`` allows to import the CV stack, and the only one that
imports ultralytics for a *drawing* reason. Everything a pose overlay decides -- the
confidence gate, the missing-keypoint sentinel, the negative-coordinate refusal, the two
filters, the one-based skeleton offset, the radius and thickness scaling, the float
truncation, the palette lookup -- lives in ``draw_plan.keypoint_ops``, which is pure
arithmetic over plain numbers and is unit-tested without a frame, a GPU or 2 GB of torch.
``keypoint_ops`` hands back ``CircleOp`` and ``LineOp`` values and this module executes
them. What is left here is a dictionary dispatch and two one-line cv2 calls, so the
answer to "why did that joint not draw?" is never in this file.

That split is also why nothing here converts anything. Coordinates arrive already
truncated to ``int``, colours already as builtin int triples, thickness already floored
at 1 -- cv2 rejects a numpy scalar in a colour slot and a float in a point, and every
conversion left in the drawing loop would be a decision that escaped ``draw_plan``.

**Three deliberate differences from the base class**, each of which would otherwise be a
silent behaviour change:

* ``conf_thres`` defaults to **0.5**, not the base class's 0.25. 0.5 is the original's
  ``if conf < 0.5`` (line 111) and the value the baseline overlay was recorded against.
* ``radius`` defaults to **5**, not ``self.lw``. The original passed 5 explicitly and
  scaled it by the frame ratio, which ``line_thickness`` and ``size_ratio`` reproduce.
* ``kpt_line=False`` is expressed as an empty ``show_skeleton``, because ``draw_plan``
  already distinguishes "unfiltered" (``None``) from "nothing survives" (empty), and a
  second way of saying the same thing is a second thing to keep in step.

**This subclass needs the cv2 backend.** ``Annotator`` chooses PIL when it is constructed
with ``pil=True``, a PIL image, or a non-ascii ``example``; ``self.im`` is then a PIL
image and the cv2 calls below raise on it. Nothing in this project constructs it that way
-- ``AnnotatingSink`` hands it a numpy BGR frame -- and the failure is loud rather than a
wrong picture, so it is documented rather than guarded.
"""
from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from typing import Any

import cv2
from ultralytics.utils.plotting import Annotator

from worksite_detector.draw_plan import CircleOp, LineOp, keypoint_ops

#: One keypoint as the caller reports it: ``(x, y)`` or ``(x, y, confidence)``, the same
#: row ``draw_plan`` takes.
_Row = Sequence[float]

#: cv2's "fill this shape" thickness. Named because ``-1`` in a thickness slot reads as a
#: mistake at the call site.
_FILLED = -1


def _draw_circle(image: Any, op: CircleOp) -> None:
    """Paint one joint dot. Every value is already an int in pixels."""
    cv2.circle(image, (op.x, op.y), op.radius, op.color, _FILLED, lineType=cv2.LINE_AA)


def _draw_line(image: Any, op: LineOp) -> None:
    """Paint one limb. Every value is already an int in pixels."""
    cv2.line(image, op.p1, op.p2, op.color, thickness=op.thickness, lineType=cv2.LINE_AA)


#: Dispatch by op type rather than by ``isinstance`` chain, so adding a third op to
#: ``draw_plan`` fails here with a ``KeyError`` naming it instead of being silently
#: skipped by an ``else`` that swallowed it.
_DRAW: dict[type, Callable[[Any, Any], None]] = {
    CircleOp: _draw_circle,
    LineOp: _draw_line,
}


class PlanAnnotator(Annotator):
    """An ``Annotator`` whose ``kpts`` draws what ``draw_plan.keypoint_ops`` decided.

    Inherits the skeleton table and the two palettes from the base class -- 19 limb pairs
    and 17 keypoint colours, which is exactly what ``keypoint_ops`` validates its inputs
    against -- and overrides nothing else. ``box_label``, ``text`` and ``result`` behave
    as they do upstream.

    One instance wraps one image and mutates it in place, which is the base class's
    contract: ``Annotator.__init__`` copies only a non-writeable array, so a caller that
    needs its frame intact passes a copy. ``AnnotatingSink`` does.
    """

    def kpts(
        self,
        kpts: Sequence[_Row],
        shape: tuple[int, int] = (640, 640),
        radius: int = 5,
        kpt_line: bool = True,
        conf_thres: float = 0.5,
        kpt_color: tuple[int, int, int] | None = None,
        *,
        line_thickness: int = 2,
        size_ratio: float = 1.0,
        show_points: Collection[int] | None = None,
        show_skeleton: Collection[Sequence[int]] | None = None,
    ) -> None:
        """Draw one person's pose onto this annotator's image.

        ``kpts`` is that person's keypoint rows, ``(x, y)`` or ``(x, y, confidence)``, and
        ``shape`` is ``(height, width)`` -- the order the base class takes it in.
        ``keypoint_ops`` accepts it and reads it nowhere; see ``draw_plan`` for why using
        it is the defect that module removes.

        ``radius`` and ``line_thickness`` are both multiplied by ``size_ratio``, which is
        the original's ``plot_size_redio``: it scales the overlay to the frame so a joint
        on a 4K frame is not a five-pixel speck. ``conf_thres`` gates each keypoint's own
        visibility score; a two-column row carries none and always draws.

        ``kpt_color`` paints every joint and limb the same BGR triple, as upstream does;
        omit it for the per-joint palettes. ``kpt_line=False`` suppresses the limbs, and
        ``show_points`` / ``show_skeleton`` filter the joints and the limbs independently
        -- an empty collection is "none of them", ``None`` is "all of them".

        Returns nothing and draws in place.

        Raises:
            ValueError: From ``keypoint_ops``, if the skeleton table or a colour palette
                cannot be read -- configuration errors, refused on the first frame rather
                than on the frame that first exposes them.
        """
        # `self.kpt_color` / `self.limb_color` are numpy rows of uint8, which cv2 rejects
        # in a colour slot; `keypoint_ops` copies whichever table it is given into builtin
        # int triples, so both branches arrive at the drawing loop in the same shape.
        point_palette = self.kpt_color if kpt_color is None else [kpt_color] * len(kpts)
        limb_palette = self.limb_color if kpt_color is None else [kpt_color] * len(self.skeleton)

        for op in keypoint_ops(
            kpts,
            shape,
            self.skeleton,
            point_palette,
            limb_palette,
            radius=radius,
            line_thickness=line_thickness,
            size_ratio=size_ratio,
            conf_threshold=conf_thres,
            show_points=show_points,
            show_skeleton=show_skeleton if kpt_line else (),
        ):
            _DRAW[type(op)](self.im, op)
