"""`adapters.UltralyticsPoseModel` / `UltralyticsObjectModel` against the real library.

**The load-bearing test in this file is `test_box_confidence_is_index_aligned_...`.**
`pipeline._gestures_of` pairs `PoseDetection.box_conf[i]` with `keypoints_xy[i]` as one
person, and publishes that confidence as the `confidencePercentage` of every gesture
event. Nothing downstream can detect the pairing being wrong: a mis-paired confidence is
a plausible number in the right range on the right chart, attached to the wrong worker.
The assumption is therefore verified against the library on real multi-person images
rather than asserted in a docstring, and the verification lives here so that an
ultralytics upgrade that reorders either row fails in CI instead of at a worksite.

The second group pins what the library does on a **person-free frame**, which is 28% of
the baseline recording. That shape is version-specific -- it is exactly what the
original's `results[0].keypoints.shape[1] == 0` guard was written against and no longer
matches -- so it is asserted rather than assumed.

The rest use hand-built result objects. Those are not doubles standing in for the model:
they are the shapes the library is *allowed* to return and that no real frame produces on
demand -- weights without visibility scores, a names table missing an index, rows that
disagree in length.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pytest
from worksite_detector.adapters import (
    AdapterUnavailableError,
    UltralyticsObjectModel,
    UltralyticsPoseModel,
)
from worksite_detector.pipeline import PoseDetection
from worksite_detector.pose_rules import PersonObservation

pytestmark = pytest.mark.requires_ultralytics

#: The original's two gates: `conf=0.8` for pose (line 291) and `conf=0.6` for PPE (293).
POSE_CONF = 0.8
PPE_CONF = 0.6

#: What `best.pt` was trained to emit. The engine has an event for all three.
PPE_LABELS = {"fall", "no-helmet", "no-jacket"}

COCO_KEYPOINTS = 17


@pytest.fixture(scope="session")
def pose_model(pose_weights) -> UltralyticsPoseModel:
    return UltralyticsPoseModel.load(pose_weights, confidence=POSE_CONF)


@pytest.fixture(scope="session")
def ppe_model(ppe_weights) -> UltralyticsObjectModel:
    return UltralyticsObjectModel.load(ppe_weights, confidence=PPE_CONF)


# --------------------------------------------------------------------------------------
# The pairing every gesture event's confidence depends on.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("image_fixture", ["crowd_image", "pair_image"])
def test_box_confidence_is_index_aligned_with_keypoints(
    image_fixture: str, pose_model: UltralyticsPoseModel, request: pytest.FixtureRequest
) -> None:
    """Person `i`'s joints must lie inside person `i`'s box, and no one else's.

    The evidence is geometric because it is the only kind available: the library hands
    back two tensors and no statement about how they correspond. If the rows were paired
    by index, each person's confident keypoints fall inside the box at the same index and
    outside the others; if they were shuffled, the diagonal of the containment matrix
    collapses. Run on four people at four scales (`bus.jpg`) and on two overlapping
    people (`zidane.jpg`), which is the case a positional pairing would most easily get
    wrong.
    """
    image = request.getfixturevalue(image_fixture)
    result = pose_model._model(image, conf=POSE_CONF, verbose=False)[0]

    boxes = result.boxes.xyxy.cpu().numpy()
    keypoints = result.keypoints.data.cpu().numpy()
    people = boxes.shape[0]
    assert people >= 2, f"{image_fixture} must hold at least two people, found {people}"
    assert keypoints.shape[0] == people, "one keypoint row per box, or there is no pairing"

    for person in range(people):
        visible = keypoints[person][:, 2] > 0.5
        if visible.sum() < 2:
            # A person the model saw as a box but barely as joints carries no geometry to
            # test with; the length equality above still covers them.
            continue
        inside = [_containment(boxes[box], keypoints[person][visible]) for box in range(people)]
        best = max(range(people), key=lambda box: inside[box])

        assert best == person, (
            f"in {image_fixture}, person {person}'s keypoints sit inside box {best}, not "
            f"box {person}. boxes.conf is NOT index-aligned with keypoints in this "
            "version, so every gesture event is publishing another worker's confidence."
        )
        assert inside[person] == pytest.approx(1.0), (
            f"person {person}'s own box should contain all of their confident keypoints, "
            f"got {inside[person]:.2f}"
        )


def _containment(box: np.ndarray, points: np.ndarray) -> float:
    """Fraction of `points` lying within `box`, with a 2% tolerance on its longest side.

    The tolerance is there because a box is regressed and the keypoints are regressed
    separately: a wrist can sit a pixel or two outside its own box without that meaning
    it belongs to someone else's. It is far smaller than the gap between two people.
    """
    x1, y1, x2, y2 = box
    padding = 0.02 * max(x2 - x1, y2 - y1)
    within = (
        (points[:, 0] >= x1 - padding)
        & (points[:, 0] <= x2 + padding)
        & (points[:, 1] >= y1 - padding)
        & (points[:, 1] <= y2 + padding)
    )
    return float(within.mean())


# --------------------------------------------------------------------------------------
# The round trip into the pipeline's boundary types.
# --------------------------------------------------------------------------------------


def test_pose_output_round_trips_into_pose_detection(
    pose_model: UltralyticsPoseModel, crowd_image: np.ndarray
) -> None:
    pose = pose_model(crowd_image)

    assert isinstance(pose, PoseDetection)
    assert len(pose.keypoints_xy) >= 2, "bus.jpg holds four people"
    assert len(pose.keypoints_xy) == len(pose.keypoint_conf) == len(pose.box_conf), (
        "the three rows are one entry per person and are paired by index"
    )
    for keypoints_xy, keypoint_conf in zip(pose.keypoints_xy, pose.keypoint_conf, strict=True):
        assert len(keypoints_xy) == COCO_KEYPOINTS
        assert len(keypoint_conf) == COCO_KEYPOINTS
        assert all(isinstance(x, float) and isinstance(y, float) for x, y in keypoints_xy), (
            "a torch scalar crossing this seam would drag torch into every rule below it"
        )
        assert all(0.0 <= conf <= 1.0 for conf in keypoint_conf)
    assert all(0.0 <= conf <= 1.0 for conf in pose.box_conf), (
        "box confidence is published verbatim, and DetectionEvent refuses anything else"
    )
    assert all(conf >= POSE_CONF for conf in pose.box_conf), (
        "the configured confidence gate has to reach the model call"
    )


def test_pose_output_is_accepted_by_the_rule_that_consumes_it(
    pose_model: UltralyticsPoseModel, crowd_image: np.ndarray
) -> None:
    # `PersonObservation` validates the row widths and the confidence range at
    # construction, so this is the pipeline's own consumer confirming the adapter's shape.
    pose = pose_model(crowd_image)

    observations = [
        PersonObservation(
            person_id=index,
            keypoints_xy=tuple(keypoints_xy),
            keypoint_conf=tuple(keypoint_conf),
            detection_confidence=box_conf,
        )
        for index, (keypoints_xy, keypoint_conf, box_conf) in enumerate(
            zip(pose.keypoints_xy, pose.keypoint_conf, pose.box_conf, strict=True)
        )
    ]

    assert len(observations) == len(pose.box_conf)


def test_a_joint_the_model_barely_saw_keeps_its_coordinates_in_this_version(
    pose_model: UltralyticsPoseModel, crowd_image: np.ndarray
) -> None:
    """8.3 does **not** write the `(0, 0)` marker, and the visibility gate is what saves us.

    `draw_plan`, `geometry` and `config` are all written around YOLO's habit of zeroing a
    keypoint it is not sure about -- 8.0.x masked `data[..., :2]` wherever the confidence
    fell below 0.5, and `Keypoints.__init__` still *documents* that it does. 8.3.253 does
    not: a joint the model is 2% sure about arrives at a plausible pixel position with a
    0.02 confidence beside it.

    Nothing is broken by that, but the reason has moved. The sentinel checks are no longer
    the thing standing between a guessed elbow and a published FRONT_BEND -- the
    `keypoint_visibility` gate is, alone, and `GestureSpec` requires it to cover every
    point of the chain it measures. This test exists so an upgrade that changes either
    behaviour is read as the safety change it is rather than as a cosmetic difference.
    """
    pose = pose_model(crowd_image)

    barely_seen = [
        (point, conf)
        for person_xy, person_conf in zip(pose.keypoints_xy, pose.keypoint_conf, strict=True)
        for point, conf in zip(person_xy, person_conf, strict=True)
        if conf < 0.5
    ]
    assert barely_seen, "bus.jpg holds people the model can only partly see"
    assert all(point != (0.0, 0.0) for point, _ in barely_seen), (
        "this version has started zeroing unsure keypoints again. That is the (0, 0) "
        "marker draw_plan and geometry refuse; their guards are live once more."
    )


# --------------------------------------------------------------------------------------
# The person-free frame: 28% of the baseline recording, and the original's fatal guard.
# --------------------------------------------------------------------------------------


def test_a_person_free_frame_yields_three_empty_rows(
    pose_model: UltralyticsPoseModel, blank_frame: np.ndarray
) -> None:
    pose = pose_model(blank_frame)

    assert pose.keypoints_xy == []
    assert pose.keypoint_conf == []
    assert pose.box_conf == []


def test_a_person_free_frame_is_an_empty_batch_of_full_width_rows(
    pose_model: UltralyticsPoseModel, blank_frame: np.ndarray
) -> None:
    """What `keypoints.data` and `keypoints.conf` actually are when nobody is found.

    Pinned because the original's guard depended on it and was wrong by this version:

        if results[0].keypoints.shape[1] == 0:   # aiModule.py line 301
            continue

    `shape` here is `(0, 17, 3)`, so `shape[1]` is 17, so the guard is **false** on a
    frame with nobody in it. The original therefore falls through to
    `results[0].keypoints.conf.tolist()[0]` on the very next lines and raises IndexError.
    The count that matters is `shape[0]`, and this adapter reads the rows rather than the
    shape so there is no number to get wrong.
    """
    result = pose_model._model(blank_frame, conf=POSE_CONF, verbose=False)[0]
    keypoints = result.keypoints

    assert keypoints is not None, "a pose model returns an empty Keypoints, never None"
    assert tuple(keypoints.data.shape) == (0, COCO_KEYPOINTS, 3)
    assert keypoints.data.tolist() == []
    assert keypoints.conf is not None, "conf is an empty tensor, not None -- None means 2D pose"
    assert tuple(keypoints.conf.shape) == (0, COCO_KEYPOINTS)
    assert keypoints.conf.tolist() == []
    assert result.boxes is not None and len(result.boxes) == 0

    assert keypoints.shape[1] != 0, (
        "the legacy guard `keypoints.shape[1] == 0` reads the keypoint *count*, not the "
        "person count, so it never fires on this version"
    )
    assert keypoints.data.shape[0] == 0, "the person count is shape[0]"


# --------------------------------------------------------------------------------------
# The PPE / fall model.
# --------------------------------------------------------------------------------------


def test_object_model_maps_class_indices_to_the_labels_the_pipeline_translates(
    ppe_model: UltralyticsObjectModel, crowd_image: np.ndarray
) -> None:
    detections = ppe_model(crowd_image)

    assert detections, "bus.jpg holds people without helmets or high-vis jackets"
    for detection in detections:
        assert detection.label in PPE_LABELS, (
            f"{detection.label!r} is not one of the three classes best.pt was trained on; "
            "pipeline._EVENT_TYPE_BY_LABEL translates exactly these"
        )
        assert PPE_CONF <= detection.confidence <= 1.0
        assert isinstance(detection.confidence, float)
        x1, y1, x2, y2 = detection.box
        assert all(isinstance(value, int) for value in detection.box)
        assert x1 < x2 and y1 < y2, f"a box must have positive area, got {detection.box}"


def test_object_model_finds_nothing_in_an_empty_frame(
    ppe_model: UltralyticsObjectModel, blank_frame: np.ndarray
) -> None:
    assert list(ppe_model(blank_frame)) == []


def test_the_confidence_gate_reaches_the_model(
    ppe_weights, crowd_image: np.ndarray
) -> None:
    # Two adapters over the same weights, differing only in the configured gate: the
    # looser one must see at least as much. This is what proves `conf` is not hardcoded.
    strict = UltralyticsObjectModel.load(ppe_weights, confidence=0.9)
    loose = UltralyticsObjectModel.load(ppe_weights, confidence=0.1)

    assert len(loose(crowd_image)) > len(strict(crowd_image))


# --------------------------------------------------------------------------------------
# Shapes the library is allowed to return that no real frame produces on demand.
# --------------------------------------------------------------------------------------


class FakeKeypoints:
    def __init__(self, data: np.ndarray, conf: np.ndarray | None) -> None:
        self.data = data
        self.conf = conf


class FakeBoxes:
    def __init__(self, conf: np.ndarray, xyxy: np.ndarray, cls: np.ndarray) -> None:
        self.conf = conf
        self.xyxy = xyxy
        self.cls = cls


class FakeResult:
    def __init__(self, keypoints: Any = None, boxes: Any = None, names: Any = None) -> None:
        self.keypoints = keypoints
        self.boxes = boxes
        self.names = names if names is not None else {}


class FakeModel:
    """Returns one scripted result, and records the keyword arguments it was called with."""

    def __init__(self, result: FakeResult) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(self, image: Any, **kwargs: Any) -> list[FakeResult]:
        self.calls.append(kwargs)
        return [self._result]

    def predict(self, image: Any, **kwargs: Any) -> list[FakeResult]:
        self.calls.append(kwargs)
        return [self._result]


def _keypoint_rows(people: int, columns: int) -> np.ndarray:
    return np.tile(
        np.arange(1.0, COCO_KEYPOINTS * columns + 1.0).reshape(COCO_KEYPOINTS, columns),
        (people, 1, 1),
    )


def test_rows_that_disagree_in_length_are_refused_at_the_seam() -> None:
    # The failure this raises for is the one no downstream check could catch: two people's
    # joints with one person's confidence would pair silently and wrongly.
    result = FakeResult(
        keypoints=FakeKeypoints(_keypoint_rows(2, 3), np.full((2, COCO_KEYPOINTS), 0.9)),
        boxes=FakeBoxes(np.array([0.9]), np.zeros((1, 4)), np.zeros(1)),
    )
    model = UltralyticsPoseModel(FakeModel(result), confidence=POSE_CONF)

    with pytest.raises(ValueError, match="paired by index"):
        model(object())


def test_weights_without_visibility_scores_are_treated_as_visible_and_warned_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # `Keypoints.conf` is None exactly when the weights report two columns per keypoint.
    # Zero would be the other reading, and it would fail every visibility gate for ever
    # while looking like a quiet site.
    result = FakeResult(
        keypoints=FakeKeypoints(_keypoint_rows(1, 2), None),
        boxes=FakeBoxes(np.array([0.9]), np.zeros((1, 4)), np.zeros(1)),
    )
    model = UltralyticsPoseModel(FakeModel(result), confidence=POSE_CONF)

    with caplog.at_level(logging.WARNING, logger="worksite_detector.adapters"):
        first = model(object())
        model(object())

    assert first.keypoint_conf == [[1.0] * COCO_KEYPOINTS]
    warnings = [record for record in caplog.records if "visibility" in record.message]
    assert len(warnings) == 1, "once per run, not once per frame at 25 frames a second"


def test_a_person_free_frame_from_visibility_free_weights_warns_about_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = FakeResult(
        keypoints=FakeKeypoints(np.zeros((0, COCO_KEYPOINTS, 2)), None),
        boxes=FakeBoxes(np.zeros(0), np.zeros((0, 4)), np.zeros(0)),
    )
    model = UltralyticsPoseModel(FakeModel(result), confidence=POSE_CONF)

    with caplog.at_level(logging.WARNING, logger="worksite_detector.adapters"):
        pose = model(object())

    assert pose.keypoint_conf == []
    assert not caplog.records, "an empty frame says nothing about the weights"


def test_a_result_without_a_detection_head_is_an_empty_observation() -> None:
    model = UltralyticsObjectModel(FakeModel(FakeResult(boxes=None)), confidence=PPE_CONF)

    assert list(model(object())) == []


def test_an_unnamed_class_index_becomes_its_own_number(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # It then matches no event type and is ignored, which is what `pipeline` already does
    # with an unknown label -- and is a great deal better than losing the frame.
    result = FakeResult(
        boxes=FakeBoxes(np.array([0.7]), np.array([[1.0, 2.0, 3.0, 4.0]]), np.array([7.0])),
        names={0: "fall"},
    )
    model = UltralyticsObjectModel(FakeModel(result), confidence=PPE_CONF)

    with caplog.at_level(logging.WARNING, logger="worksite_detector.adapters"):
        detections = list(model(object()))

    assert [detection.label for detection in detections] == ["7"]
    assert caplog.records, "an unnamed class is worth one line in the log"


def test_the_models_are_called_the_way_the_original_called_them() -> None:
    pose_backend = FakeModel(
        FakeResult(
            keypoints=FakeKeypoints(_keypoint_rows(0, 3), np.zeros((0, COCO_KEYPOINTS))),
            boxes=FakeBoxes(np.zeros(0), np.zeros((0, 4)), np.zeros(0)),
        )
    )
    ppe_backend = FakeModel(FakeResult(boxes=FakeBoxes(np.zeros(0), np.zeros((0, 4)), np.zeros(0))))

    UltralyticsPoseModel(pose_backend, confidence=0.8)(object())
    UltralyticsObjectModel(ppe_backend, confidence=0.6)(object())

    assert pose_backend.calls == [{"conf": 0.8, "verbose": False}]
    assert ppe_backend.calls == [{"show": False, "conf": 0.6, "verbose": False}]


def test_missing_weights_are_refused_without_downloading_anything(tmp_path) -> None:
    # `YOLO("yolov8s-pose.pt")` on a missing file fetches it from the internet, so a
    # mistyped path would silently run a detector on weights nobody chose.
    missing = tmp_path / "yolov8s-pose.pt"

    with pytest.raises(AdapterUnavailableError) as excinfo:
        UltralyticsPoseModel.load(missing, confidence=POSE_CONF)

    assert str(missing) in str(excinfo.value)
    assert not missing.exists(), "nothing may be downloaded in place of the configured file"
