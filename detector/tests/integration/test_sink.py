"""`adapters.AnnotatingSink`: the file the browser polls, and the defect it fixes.

The engine's `EventController.getImage` serves one file and `web/src/pages/VideoStream.js`
re-fetches it every 100 ms. The original wrote that file with `cv2.imwrite` straight onto
the served path, once per frame -- so a reader arriving mid-encode got a truncated JPEG.
This is not a theoretical window: at 25 frames a second, writing a few hundred kilobytes
each time, it is open for a large fraction of every second.

`test_the_target_is_never_a_partial_image` is the test that defect exists for. The others
pin the two behaviours around it -- that a frame is written *at all* on a person-free
frame, which the original's `continue` skipped, and that the caller's frame survives being
annotated.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import cv2
import numpy as np
import pytest
from worksite_detector.adapters import AdapterUnavailableError, AnnotatingSink
from worksite_detector.pipeline import Frame, ObjectDetection, PoseDetection

pytestmark = pytest.mark.requires_ultralytics

COCO_KEYPOINTS = 17
CONFIDENT = 0.99

EMPTY_POSE = PoseDetection(keypoints_xy=[], keypoint_conf=[], box_conf=[])


def _frame(image: np.ndarray, index: int = 0, timestamp_ms: int = 0) -> Frame:
    return Frame(image=image, timestamp_ms=timestamp_ms, index=index)


def _person(x: float = 300.0, y: float = 200.0) -> PoseDetection:
    """One person whose 17 joints march diagonally across the frame."""
    return PoseDetection(
        keypoints_xy=[[(x + 10 * i, y + 5 * i) for i in range(COCO_KEYPOINTS)]],
        keypoint_conf=[[CONFIDENT] * COCO_KEYPOINTS],
        box_conf=[0.95],
    )


def _decode(path: Path) -> np.ndarray | None:
    raw = path.read_bytes()
    if not raw:
        return None
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


@pytest.fixture()
def photo() -> np.ndarray:
    """A frame with enough detail to encode into a non-trivial number of bytes."""
    rng = np.random.default_rng(20240804)
    return rng.integers(0, 256, (540, 960, 3), dtype=np.uint8)


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    return tmp_path / "output_image.jpg"


def test_writes_a_decodable_image(target: Path, photo: np.ndarray) -> None:
    sink = AnnotatingSink(target)
    try:
        sink.write(_frame(photo), _person(), [])
    finally:
        sink.close()

    decoded = _decode(target)
    assert decoded is not None, "the served file must be a complete, decodable image"
    assert decoded.shape[2] == 3


def test_the_target_is_never_a_partial_image(target: Path, photo: np.ndarray) -> None:
    """A reader polling the target sees whole frames only, never half of one.

    The poller is the browser: it reads the file over and over while frames are written
    underneath it, and every read that returns bytes has to decode into an image. Written
    straight onto the target -- as the original did -- this fails, because `cv2.imwrite`
    truncates the file and then fills it, and a reader arriving in between gets a JPEG
    with its tail missing. Written through `os.replace`, a read returns either the
    previous frame whole or the new frame whole.

    **Two Windows artifacts are not failures of that contract, and are counted instead.**
    Renaming over an open file, and opening a file being renamed over, each raise a
    sharing violation for the moment the rename takes; the reader then observes *nothing*
    rather than half an image, which is the guarantee under test. This poller is also a
    harsher client than the real one: Python's `open` denies the delete share, while the
    engine reads through Java NIO, which does not, so neither side of this collision
    happens in production. What the two collisions rule out is any implementation where a
    reader could see the file mid-encode.
    """
    sink = AnnotatingSink(target)
    stop = threading.Event()
    partial: list[str] = []
    whole = 0
    blocked = 0

    def poll() -> None:
        nonlocal whole, blocked
        while not stop.is_set():
            try:
                raw = target.read_bytes()
            except FileNotFoundError:
                # Before the first frame; `os.replace` never leaves this gap afterwards.
                continue
            except PermissionError:
                blocked += 1
                continue
            if not raw:
                partial.append("the target was an empty file")
                continue
            if cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR) is None:
                partial.append(f"the target was {len(raw)} undecodable bytes")
                continue
            whole += 1

    reader = threading.Thread(target=poll, daemon=True)
    reader.start()
    try:
        for index in range(60):
            sink.write(_frame(photo, index=index), _person(x=float(index * 4)), [])
    finally:
        stop.set()
        reader.join(timeout=5)
        sink.close()

    assert not partial, f"the browser saw a half-written frame: {partial[:3]}"
    assert whole > 0, f"the poller never read a whole frame at all ({blocked} were blocked)"
    assert whole > blocked, (
        f"only {whole} of {whole + blocked} reads got through; the rename is holding the "
        "target open far longer than the moment it should take"
    )


def test_a_write_leaves_no_temporary_file_behind(target: Path, photo: np.ndarray) -> None:
    # The temporary is renamed *onto* the target rather than copied, so nothing is left to
    # collect, and the served directory does not fill up over a night shift.
    sink = AnnotatingSink(target)
    try:
        sink.write(_frame(photo), EMPTY_POSE, [])
    finally:
        sink.close()

    assert [path.name for path in target.parent.iterdir()] == [target.name]


def test_a_frame_with_nobody_and_nothing_in_it_is_still_written(
    target: Path, photo: np.ndarray
) -> None:
    # The frozen-preview defect: the original's `continue` (line 310) skipped the write on
    # every person-free frame, so an empty site looked exactly like a dead camera.
    sink = AnnotatingSink(target)
    try:
        sink.write(_frame(photo), EMPTY_POSE, [])
    finally:
        sink.close()

    assert _decode(target) is not None


def test_each_frame_replaces_the_last(target: Path, photo: np.ndarray) -> None:
    dark = np.zeros_like(photo)
    sink = AnnotatingSink(target)
    try:
        sink.write(_frame(photo), EMPTY_POSE, [])
        bright_bytes = target.read_bytes()
        sink.write(_frame(dark, index=1), EMPTY_POSE, [])
    finally:
        sink.close()

    assert target.read_bytes() != bright_bytes
    decoded = _decode(target)
    assert decoded is not None and decoded.mean() < 8, "the preview should now be the dark frame"


def test_the_caller_s_frame_is_not_annotated_in_place(target: Path, photo: np.ndarray) -> None:
    # `Annotator` draws into the array it is handed, and `frame.image` belongs to the
    # capture. A sink that drew on it would corrupt anything reading the frame after it.
    original = photo.copy()
    sink = AnnotatingSink(target)
    try:
        sink.write(_frame(photo), _person(), [ObjectDetection("no-helmet", 0.8, (10, 10, 90, 90))])
    finally:
        sink.close()

    assert np.array_equal(photo, original)


def test_the_pose_is_drawn(target: Path) -> None:
    black = np.zeros((540, 960, 3), np.uint8)
    sink = AnnotatingSink(target, max_dimension=None)
    try:
        sink.write(_frame(black), _person(), [])
    finally:
        sink.close()

    decoded = _decode(target)
    assert decoded is not None
    assert decoded.any(), "a person's skeleton should have been painted onto a black frame"


def test_violation_boxes_are_drawn_over_the_skeleton(target: Path) -> None:
    black = np.zeros((540, 960, 3), np.uint8)
    sink = AnnotatingSink(target, max_dimension=None)
    try:
        sink.write(
            _frame(black), EMPTY_POSE, [ObjectDetection("no-helmet", 0.8, (100, 100, 400, 400))]
        )
    finally:
        sink.close()

    decoded = _decode(target)
    assert decoded is not None
    # Sampled on the *bottom* edge of the rectangle: the label is white and is drawn at the
    # box's top-left corner, so only the bottom edge is green and nothing else. JPEG is
    # lossy, hence a dominance test rather than an exact colour.
    edge = decoded[395:405, 150:350]
    assert int(edge[:, :, 1].max()) > int(edge[:, :, 0].max()) + 40, (
        "the violation box should be green, as the original drew it"
    )
    assert decoded[:, :, :].any(), "and something must have been drawn at all"


def test_the_longest_side_is_scaled_for_the_polling_browser(
    target: Path, photo: np.ndarray
) -> None:
    sink = AnnotatingSink(target, max_dimension=320)
    try:
        sink.write(_frame(photo), EMPTY_POSE, [])
    finally:
        sink.close()

    decoded = _decode(target)
    assert decoded is not None
    assert max(decoded.shape[:2]) == 320


def test_max_dimension_none_writes_the_frame_at_its_own_size(
    target: Path, photo: np.ndarray
) -> None:
    sink = AnnotatingSink(target, max_dimension=None)
    try:
        sink.write(_frame(photo), EMPTY_POSE, [])
    finally:
        sink.close()

    decoded = _decode(target)
    assert decoded is not None
    assert decoded.shape[:2] == photo.shape[:2]


def test_a_path_without_an_extension_is_refused_at_startup(tmp_path: Path) -> None:
    # OpenCV picks its encoder from the extension, so this would fail on the first frame
    # of a night shift rather than at the moment the configuration was read.
    with pytest.raises(AdapterUnavailableError, match="extension"):
        AnnotatingSink(tmp_path / "output_image")


def test_the_output_directory_is_created(tmp_path: Path, photo: np.ndarray) -> None:
    target = tmp_path / "previews" / "camera-1" / "output_image.jpg"

    sink = AnnotatingSink(target)
    try:
        sink.write(_frame(photo), EMPTY_POSE, [])
    finally:
        sink.close()

    assert _decode(target) is not None


def test_an_unencodable_extension_leaves_the_target_untouched(
    tmp_path: Path, photo: np.ndarray
) -> None:
    # Encoding happens entirely in memory before anything on disk is touched, so a failure
    # costs one frame and the operator keeps looking at the last good picture.
    target = tmp_path / "output_image.zzz"
    sink = AnnotatingSink(target)
    try:
        with pytest.raises(Exception):  # noqa: B017 -- cv2.error or RuntimeError, both fine
            sink.write(_frame(photo), EMPTY_POSE, [])
    finally:
        sink.close()

    assert not target.exists()


def test_close_removes_a_stray_temporary_and_keeps_the_last_frame(
    target: Path, photo: np.ndarray
) -> None:
    sink = AnnotatingSink(target)
    sink.write(_frame(photo), EMPTY_POSE, [])
    stray = sink._temporary
    stray.write_bytes(b"half a frame from a process that was killed")

    sink.close()
    sink.close()

    assert not stray.exists(), "a killed write must not leave rubbish in the served directory"
    assert _decode(target) is not None, (
        "the target is the last frame the operator saw; closing must not delete it"
    )


def test_two_processes_do_not_share_a_temporary_file(target: Path) -> None:
    # One fixed name per process rather than per frame: a crash leaves at most one stray,
    # and two detectors sharing an output directory cannot overwrite each other's.
    sink = AnnotatingSink(target)
    try:
        assert str(os.getpid()) in sink._temporary.name
        assert sink._temporary.parent == target.parent, (
            "os.replace is only atomic within a directory"
        )
    finally:
        sink.close()
