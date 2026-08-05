"""Build the demo clip the compose stack feeds the detector.

The clip is generated rather than committed. It is synthetic -- assembled from the two
sample photographs that ship inside the ``ultralytics`` package, because no real worksite
footage is redistributable -- so committing five megabytes of it would put a binary that
proves nothing about real sites into a repository whose history was rewritten specifically
to get binaries out of it. That history reached 250 MB one reasonable-looking file at a
time, and this is what that looks like at the beginning.

It does produce genuine detections: the people in those photographs are found by the pose
model, and the PPE model finds violations on them, which is enough to drive every stage of
the pipeline end to end.

Usage::

    python demo/make_clip.py                     # writes demo/worksite.mp4
    python demo/make_clip.py --out other.mp4 --seconds 40

Requires the detector's ``cv`` extra (``pip install -e 'detector[cv]'``), which is where
opencv and ultralytics come from.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Frames per second written into the container. The detector reads timestamps from the
# file's media position, so this is also what decides how long a violation appears to last:
# at 25 fps a subject held for 100 frames is a four-second violation, which clears the
# engine's 3000 ms floor with room to spare.
FPS = 25

# Every clip carries a stretch with nobody in it. That is not padding -- it is the case the
# original detector skipped the whole frame over, losing a fall and freezing the preview, so
# a demo that never shows an empty frame never exercises the fix.
EMPTY_FRACTION = 0.25


def build(out: Path, seconds: float, width: int, height: int) -> int:
    try:
        import cv2
        import ultralytics
    except ImportError as exc:  # pragma: no cover - depends on the optional extra
        print(
            f"demo/make_clip.py needs the detector's 'cv' extra ({exc.name} is missing).\n"
            "Install it with:  pip install -e 'detector[cv]'",
            file=sys.stderr,
        )
        return 2

    assets = Path(ultralytics.__file__).parent / "assets"
    sources = [assets / "bus.jpg", assets / "zidane.jpg"]
    missing = [p for p in sources if not p.is_file()]
    if missing:
        print(
            "the ultralytics sample images are not where they were expected:\n  "
            + "\n  ".join(str(p) for p in missing)
            + "\nThey ship inside the package, so this usually means a partial install.",
            file=sys.stderr,
        )
        return 3

    images = []
    for path in sources:
        frame = cv2.imread(str(path))
        if frame is None:
            print(f"cv2 could not decode {path}", file=sys.stderr)
            return 3
        images.append(cv2.resize(frame, (width, height)))

    total = int(seconds * FPS)
    empty = images[0].copy()
    empty[:] = (32, 32, 32)

    out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (width, height))
    if not writer.isOpened():
        print(f"cv2 could not open {out} for writing", file=sys.stderr)
        return 3

    try:
        # Two populated stretches with an empty one between them, so the clip exercises a
        # violation window opening, a person-free stretch closing it, and a second window.
        populated = int(total * (1 - EMPTY_FRACTION) / 2)
        blank = total - 2 * populated
        for _ in range(populated):
            writer.write(images[0])
        for _ in range(blank):
            writer.write(empty)
        for _ in range(total - populated - blank):
            writer.write(images[1])
    finally:
        writer.release()

    size_mb = out.stat().st_size / 1_048_576
    print(f"wrote {out} -- {total} frames, {seconds:g}s at {FPS}fps, {size_mb:.1f} MB")
    print(
        "This clip is synthetic. It drives the pipeline; it is not evidence about real "
        "worksites. Replace it with real footage by pointing DEMO_VIDEO_DIR and DEMO_VIDEO "
        "at your own file."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "worksite.mp4")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    args = parser.parse_args(argv)
    return build(args.out, args.seconds, args.width, args.height)


if __name__ == "__main__":
    raise SystemExit(main())
