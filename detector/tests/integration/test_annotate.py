"""`annotate.PlanAnnotator` against a real image buffer and the real ultralytics tables.

What is *decided* about a pose overlay is pinned by `tests/test_draw_plan.py`, which runs
without cv2, without torch and in milliseconds. Nothing here re-tests a confidence gate or
a coordinate rule. These tests ask the three questions that only a real frame can answer:

* Does the buffer survive? A drawing loop that changed a frame's shape or dtype would
  corrupt every stage after it, and cv2 rejects the values `draw_plan` exists to convert.
* Does the delegation actually happen? Every assertion below about *what did not draw* is
  a `draw_plan` decision observed through pixels -- proof that the two halves are joined,
  which neither half can show on its own.
* Does the base class still fit? `self.skeleton`, `self.kpt_color` and `self.limb_color`
  come from ultralytics and are what `keypoint_ops` validates its input against; a version
  that renamed or resized one of them fails here rather than at a customer site.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest
from worksite_detector.annotate import PlanAnnotator

pytestmark = pytest.mark.requires_ultralytics

# COCO indices, so a keypoint list below reads as a body rather than as numbers.
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
CONFIDENT = 0.99
INVISIBLE = 0.01

#: The `[6, 7]` limb of the ultralytics skeleton joins the two shoulders (one-based), and
#: it is the one limb below whose two endpoints are both drawn.
SHOULDER_LIMB = [6, 7]


def _pose(**overrides: tuple[float, float, float]) -> list[tuple[float, float, float]]:
    """17 keypoint rows, all of them YOLO's `(0, 0)` "not found" marker except the named.

    Written this way so each test states only the joints it is about; the sentinel rows
    are what `draw_plan` refuses, so an unstated joint draws nothing.
    """
    rows = [(0.0, 0.0, CONFIDENT) for _ in range(17)]
    for index, row in overrides.items():
        rows[int(index.removeprefix("k"))] = row
    return rows


def _painted(image: np.ndarray) -> int:
    """How many pixels are not still black."""
    return int(np.count_nonzero(image.any(axis=2)))


@pytest.fixture()
def frame() -> np.ndarray:
    """A black 480x640 BGR frame, so anything drawn on it is countable."""
    return np.zeros((480, 640, 3), np.uint8)


def test_draws_on_a_real_frame_without_changing_its_shape_or_dtype(frame: np.ndarray) -> None:
    before_shape, before_dtype = frame.shape, frame.dtype

    annotator = PlanAnnotator(frame)
    annotator.kpts(_pose(k5=(200.0, 150.0, CONFIDENT), k6=(300.0, 150.0, CONFIDENT)), (480, 640))
    result = annotator.result()

    assert _painted(frame) > 0, "nothing was drawn at all"
    assert result.shape == before_shape
    assert result.dtype == before_dtype
    assert result.dtype == np.uint8, "cv2 needs an 8-bit BGR buffer; anything else is a bug"


def test_draws_in_place_so_the_sink_must_pass_a_copy(frame: np.ndarray) -> None:
    # `Annotator.__init__` copies only a non-writeable array, so a caller that needs its
    # own frame intact has to copy first. `AnnotatingSink` does, and this is why.
    annotator = PlanAnnotator(frame)
    annotator.kpts(_pose(k5=(100.0, 100.0, CONFIDENT)), (480, 640))

    assert _painted(frame) > 0
    assert annotator.result() is frame or np.shares_memory(annotator.result(), frame)


def test_a_keypoint_yolo_never_found_is_not_drawn(frame: np.ndarray) -> None:
    # Every row is the exact `(0, 0)` marker, at full confidence. A drawing loop that
    # trusted the coordinates would put 17 dots in the top-left corner of every frame.
    PlanAnnotator(frame).kpts(_pose(), (480, 640))

    assert _painted(frame) == 0


def test_a_keypoint_below_the_confidence_gate_is_not_drawn(frame: np.ndarray) -> None:
    PlanAnnotator(frame).kpts(_pose(k5=(200.0, 150.0, INVISIBLE)), (480, 640))

    assert _painted(frame) == 0


def test_a_detection_on_the_top_edge_is_drawn(frame: np.ndarray) -> None:
    # The regression `draw_plan` exists for: the original's `x % shape[1] != 0 and
    # y % shape[0] != 0` threw away any keypoint whose coordinate was a multiple of the
    # frame's width or height, so a real detection on the top edge vanished.
    PlanAnnotator(frame).kpts(_pose(k5=(320.0, 0.0, CONFIDENT)), (480, 640))

    assert _painted(frame) > 0


def test_kpt_line_false_draws_the_joints_and_not_the_limb(frame: np.ndarray) -> None:
    shoulders = _pose(k5=(200.0, 150.0, CONFIDENT), k6=(400.0, 150.0, CONFIDENT))
    with_limb = frame.copy()

    PlanAnnotator(with_limb).kpts(shoulders, (480, 640), kpt_line=True)
    PlanAnnotator(frame).kpts(shoulders, (480, 640), kpt_line=False)

    assert _painted(frame) > 0, "the two joints should still be drawn"
    assert _painted(frame) < _painted(with_limb), "the limb between them should not be"


def test_show_skeleton_selects_one_limb(frame: np.ndarray) -> None:
    shoulders = _pose(k5=(200.0, 150.0, CONFIDENT), k6=(400.0, 150.0, CONFIDENT))
    everything = frame.copy()

    PlanAnnotator(everything).kpts(shoulders, (480, 640))
    PlanAnnotator(frame).kpts(shoulders, (480, 640), show_skeleton=[SHOULDER_LIMB])

    # The two frames agree here only because the shoulder limb is the sole limb whose
    # endpoints are both real; the filter is proven by the *empty* case below.
    assert _painted(frame) == _painted(everything)


def test_an_empty_skeleton_filter_draws_no_limb_at_all(frame: np.ndarray) -> None:
    # `None` means unfiltered and `()` means nothing survives -- different answers, which
    # is why `draw_plan` tests `is None` rather than truthiness.
    shoulders = _pose(k5=(200.0, 150.0, CONFIDENT), k6=(400.0, 150.0, CONFIDENT))
    unfiltered = frame.copy()

    PlanAnnotator(unfiltered).kpts(shoulders, (480, 640))
    PlanAnnotator(frame).kpts(shoulders, (480, 640), show_skeleton=())

    assert 0 < _painted(frame) < _painted(unfiltered)


def test_show_points_selects_which_joints_draw(frame: np.ndarray) -> None:
    shoulders = _pose(k5=(200.0, 150.0, CONFIDENT), k6=(400.0, 150.0, CONFIDENT))
    both = frame.copy()

    PlanAnnotator(both).kpts(shoulders, (480, 640), kpt_line=False)
    PlanAnnotator(frame).kpts(
        shoulders, (480, 640), kpt_line=False, show_points=[LEFT_SHOULDER]
    )

    assert 0 < _painted(frame) < _painted(both)


def test_size_ratio_scales_the_overlay_to_the_frame(frame: np.ndarray) -> None:
    joint = _pose(k5=(200.0, 150.0, CONFIDENT))
    small = frame.copy()

    PlanAnnotator(small).kpts(joint, (480, 640), size_ratio=1.0)
    PlanAnnotator(frame).kpts(joint, (480, 640), size_ratio=4.0)

    assert _painted(frame) > _painted(small), "a 4K frame needs more than a five-pixel speck"


def test_a_uniform_colour_reaches_cv2_as_cv2_accepts_it(frame: np.ndarray) -> None:
    # The palettes are numpy rows of uint8, which cv2 rejects in a colour slot; a caller
    # passing plain ints must reach the buffer unchanged. Pure red on black, so every
    # painted pixel -- antialiased edges included -- can only be red.
    PlanAnnotator(frame).kpts(
        _pose(k5=(200.0, 150.0, CONFIDENT), k6=(400.0, 150.0, CONFIDENT)),
        (480, 640),
        kpt_color=(0, 0, 255),
    )

    assert _painted(frame) > 0
    assert frame[:, :, 0].max() == 0, "nothing should have been painted into the blue channel"
    assert frame[:, :, 1].max() == 0, "nothing should have been painted into the green channel"
    assert frame[:, :, 2].max() > 0


def test_the_palettes_inherited_from_ultralytics_still_fit_the_pose_model() -> None:
    # `keypoint_ops` refuses a palette shorter than what it must colour, and these three
    # tables are the base class's. A version that resized one of them fails here.
    annotator = PlanAnnotator(np.zeros((64, 64, 3), np.uint8))

    assert len(annotator.kpt_color) >= 17, "17 COCO keypoints need 17 colours"
    assert len(annotator.limb_color) >= len(annotator.skeleton)
    assert all(len(pair) == 2 for pair in annotator.skeleton)
    assert all(1 <= index <= 17 for pair in annotator.skeleton for index in pair), (
        "the skeleton table is one-based into 17 keypoints; `draw_plan` refuses a 0"
    )


def test_a_person_free_frame_draws_nothing_and_does_not_raise(frame: np.ndarray) -> None:
    # 278 of the baseline clip's 986 frames. The preview must still be written for them,
    # so the annotator has to accept an empty pose without complaint.
    PlanAnnotator(frame).kpts([], (480, 640))

    assert _painted(frame) == 0


def test_a_real_photograph_keeps_every_pixel_it_was_not_asked_to_change(
    crowd_image: np.ndarray,
) -> None:
    # A real JPEG rather than a synthetic frame: contiguity, channel count and writeability
    # are all things `Annotator.__init__` asserts on, and only a decoded image exercises.
    image = crowd_image.copy()
    original = image.copy()

    annotator = PlanAnnotator(image)
    annotator.kpts(_pose(k5=(300.0, 500.0, CONFIDENT)), image.shape[:2])
    result = annotator.result()

    assert result.shape == original.shape
    assert result.dtype == original.dtype
    changed = np.count_nonzero(np.any(result != original, axis=2))
    assert 0 < changed < original[:, :, 0].size // 100, (
        "one joint should repaint a handful of pixels, not the photograph"
    )
    assert cv2.imencode(".jpg", result)[0], "the annotated buffer must still be encodable"
