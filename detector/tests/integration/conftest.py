"""The tier that runs the real thing: real OpenCV, real weights, real tensors.

Everything in this directory exercises `adapters.py` and `annotate.py`, the two modules
`tests/test_architecture.py` exempts from the no-heavy-imports rule. The rest of the
suite runs in under a second precisely because those two are the only ones that need a
camera stack; these tests are what keeps them honest anyway.

The `importorskip` calls below are at module scope so the *whole directory* skips on a
machine without the CV extra, rather than every module in it erroring during collection.
Weights are a separate question: they are gitignored (50 MB of `best.pt`), so the
fixtures that need them skip individually and the tests that do not still run.

Every module here is marked `requires_ultralytics`, so the fast tier is
`pytest -m "not requires_ultralytics"` and this one is `pytest -m requires_ultralytics`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("cv2", reason="the integration tier needs opencv-python (the [cv] extra)")
pytest.importorskip("numpy", reason="the integration tier needs numpy (via opencv-python)")
pytest.importorskip("ultralytics", reason="the integration tier needs ultralytics (the [cv] extra)")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from ultralytics.utils import ASSETS  # noqa: E402

#: The pose model's own sample images, which ship inside the installed package. `bus.jpg`
#: holds four people and `zidane.jpg` two, which is what the index-alignment evidence in
#: `test_models.py` needs and what no synthetic frame can provide -- a pose model finds
#: nothing in a generated rectangle.
CROWD_IMAGE = ASSETS / "bus.jpg"
PAIR_IMAGE = ASSETS / "zidane.jpg"

#: Frames per second of every generated clip. 10 makes each frame 100 ms apart, which is
#: far enough to read a `CAP_PROP_POS_MSEC` sequence at a glance.
CLIP_FPS = 10.0

_DETECTOR_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def pose_weights() -> Path:
    """Path to the pose weights, or a skip if this machine has none."""
    return _weights("yolov8s-pose.pt")


@pytest.fixture(scope="session")
def ppe_weights() -> Path:
    """Path to the PPE/fall weights, or a skip if this machine has none."""
    return _weights("best.pt")


def _weights(name: str) -> Path:
    path = _DETECTOR_ROOT / "models" / name
    if not path.is_file():
        pytest.skip(f"{path} is not present; model weights are gitignored")
    return path


@pytest.fixture(scope="session")
def crowd_image() -> np.ndarray:
    """`bus.jpg` as a BGR frame: four people, at four different scales."""
    return _read(CROWD_IMAGE)


@pytest.fixture(scope="session")
def pair_image() -> np.ndarray:
    """`zidane.jpg` as a BGR frame: two people, overlapping."""
    return _read(PAIR_IMAGE)


def _read(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    assert image is not None, f"cannot read {path}, which ships inside the ultralytics package"
    return image


@pytest.fixture(scope="session")
def blank_frame() -> np.ndarray:
    """A frame with nobody in it -- 278 of the baseline clip's 986 frames were this."""
    return np.zeros((480, 640, 3), np.uint8)


@pytest.fixture(scope="session")
def counting_clip(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[int]]:
    """A real 8-frame video file, and the per-frame fill values it was written from.

    Generated rather than committed: a checked-in clip is a binary blob whose contents
    nobody can review, and everything these tests ask of a video -- that it decodes, that
    its frames arrive in order, that its media clock advances -- a generated one answers.

    The fill values increase frame by frame so a decoded frame can be placed in the clip
    by its mean brightness, which survives the codec's loss where an exact pixel does not.
    """
    path = tmp_path_factory.mktemp("clips") / "counting.mp4"
    fills = [10 * (i + 1) for i in range(8)]
    _write_clip(path, [np.full((64, 96, 3), fill, np.uint8) for fill in fills])
    return path, fills


@pytest.fixture(scope="session")
def crowd_clip(tmp_path_factory: pytest.TempPathFactory, crowd_image: np.ndarray) -> Path:
    """A real 3-frame video of `bus.jpg`, for running the models over a file.

    Scaled to half size: the models are the slow part of this tier and four people at
    405x540 are still four people.
    """
    path = tmp_path_factory.mktemp("clips") / "crowd.mp4"
    frame = cv2.resize(crowd_image, (0, 0), fx=0.5, fy=0.5)
    _write_clip(path, [frame] * 3)
    return path


def _write_clip(path: Path, frames: list[np.ndarray]) -> None:
    height, width = frames[0].shape[:2]
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), CLIP_FPS, (width, height)
    )
    assert writer.isOpened(), f"this OpenCV build cannot write {path}"
    for frame in frames:
        writer.write(frame)
    writer.release()
    assert path.is_file() and path.stat().st_size > 0, f"{path} was not written"
