"""The layer that touches the real world, and the only one in this package that may.

Everything else here is arithmetic over plain numbers: ``pipeline`` moves ``Frame``,
``PoseDetection`` and ``ObjectDetection`` values between rules that know nothing about
tensors, and ``tests/test_architecture.py`` proves it by reading the AST of every other
module. This file is where that ends. It holds the four things that cannot be expressed
without the CV stack, one class each, so that the rest of the package can be developed
and tested in under a second on a machine with no camera, no weights and no torch:

* ``OpenCvFrameSource`` isolates ``cv2.VideoCapture`` -- opening a camera or a file,
  reading frames, and above all **deciding what time a frame happened**.
* ``UltralyticsPoseModel`` and ``UltralyticsObjectModel`` isolate ``YOLO``. Their whole
  job is to turn two tensors into two lists of builtin floats, because a torch tensor
  crossing into ``pipeline`` would drag torch into every test that touches a frame.
* ``AnnotatingSink`` isolates ``cv2.imencode`` and the one file the web app polls.

**Nothing here imports ultralytics at module scope.** Each of the three places that needs
it imports it in the function that needs it and wraps the ``ImportError`` in
``AdapterUnavailableError``, which is the same rule and the same reason as
``KafkaEventPublisher.connect``: a missing optional dependency must be reported once, at
startup, by the component that wanted it, with the install command in the message --
never as a bare ``ModuleNotFoundError`` out of the middle of an import chain the operator
did not write. ``cv2`` *is* imported at module scope, because it costs a fraction of a
second and there is nothing useful to say about its absence that the import does not;
ultralytics costs seconds, pulls torch, and has an install command worth printing.

**The time a frame happened is a decision, and it is made here.** ``pipeline`` stamps
every event with ``Frame.timestamp_ms`` and reads its clock exactly once, at shutdown, so
this module is the only thing that decides what a frame's time *is*:

* A **video file** is stamped from ``CAP_PROP_POS_MSEC`` -- position within the media,
  from 0. Replaying the same file twice therefore produces byte-identical event times,
  which is what makes the baseline differential in ``tests/data/baseline`` a fixed
  comparison rather than a race against wall-clock jitter, and it is what
  ``tools/capture_trace.py`` recorded the baseline trace with.
* A **camera** has no media position, so it is stamped from the injected clock.

The consequence is stated here rather than discovered later: a file-sourced run publishes
times measured from the start of the clip, not from the epoch. Every duration, throttle
and window in the pipeline is a *difference* of two such stamps and is therefore correct
either way, but the absolute ``startTime`` a replay stores in MongoDB is media time and
will land in 1970 on the dashboard. That is the right trade for a replay -- reproducible
beats plausible -- and it is why the camera path, which is the one that feeds the live
dashboard, does not share it.

Known limitation, for the reader who meets it before this docstring does: an **RTSP or
HTTP stream** is not numeric, so it takes the media-time branch, and a live stream that
reports no position will stamp every frame with the same number. That collapses every
window and every throttle. It is left as it is because the original's ``isnumeric()``
branch is what operators' configurations were written against, and because no rule
inferred from a value this module cannot verify would be better than a documented one.
Give such a source a numeric camera index, or point it at a recorded file.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import cv2

from worksite_detector.pipeline import Frame, ObjectDetection, PoseDetection

# `worksite_detector.adapters`, which an operator raises or silences independently of the
# frame loop and of the publisher.
_LOGGER = logging.getLogger(__name__)

#: The frame the original's overlay was sized for: ``max(w / 960, h / 540)`` is its
#: ``plot_size_redio`` (line 288), which scales joint radius and limb thickness so the
#: skeleton stays legible at any resolution.
_OVERLAY_REFERENCE_WIDTH = 960
_OVERLAY_REFERENCE_HEIGHT = 540

#: The violation box and its label, as the original drew them (lines 456-458): a green
#: rectangle two pixels thick, and the raw model class in white above its top-left corner.
_BOX_COLOR = (0, 255, 0)
_BOX_THICKNESS = 2
_LABEL_COLOR = (255, 255, 255)
_LABEL_SCALE = 1.0
_LABEL_THICKNESS = 2

#: The longest side of the written preview, from ``scale = 640 / max(...)`` (line 519).
_DEFAULT_MAX_DIMENSION = 640

#: How hard to try to rename the finished frame over the one a reader is holding open.
#: Five waits of 2 ms is 10 ms at the very end of a frame whose budget is 40, and it is
#: bounded on purpose: a file held open permanently must not stall the detector.
_REPLACE_ATTEMPTS = 5
_REPLACE_BACKOFF_SECONDS = 0.002

_INSTALL_HINT = (
    "install the CV extra with `pip install -e .[cv]` (ultralytics, opencv-python and "
    "kafka-python-ng), or run the detector against a recorded trace instead"
)


class AdapterUnavailableError(RuntimeError):
    """A real-world resource could not be opened at all: a camera, a file, weights.

    One class for all four failures because they share a caller and a moment. Every one
    of them happens during startup, in the composition root, and the response to each is
    the same -- report it and do not start -- so a caller distinguishing them would only
    be re-deciding what the message already says.

    A ``RuntimeError``, and deliberately not an ``ImportError`` even when an import is
    what failed, for the reason ``PublisherUnavailableError`` is not one: the entry point
    catches ``RuntimeError`` at startup, and it must be able to name and catch this
    without importing the very package that is missing.
    """


class OpenCvFrameSource:
    """Frames from a camera index or a video file, with the time each one happened.

    Wraps exactly one ``cv2.VideoCapture``. Single pass and not reusable: iterating a
    second time continues where the capture left off while restarting ``Frame.index`` at
    zero, so it is iterated once, by one pipeline, and then closed.

    The original decided camera-versus-file with ``args.input.isnumeric()`` (line 236) and
    that is kept verbatim, because it is the rule every existing configuration was written
    against. What is *not* kept is what followed it: the original never asked whether the
    capture opened. ``while cap.isOpened()`` on a mistyped path is immediately false, so
    the detector exited with status 0, having watched nothing, printing nothing. Opening
    is checked here and a failure is fatal at startup.
    """

    def __init__(self, source: str, *, clock: Callable[[], int]) -> None:
        """Open ``source`` and choose the clock its frames will be stamped from.

        ``source`` is a camera index as a string (``"0"``), or a path or URL. ``clock``
        returns milliseconds since the epoch and is used only on the camera branch; a
        video file is stamped from its own media position instead. See the module
        docstring for why that split exists and what it costs.

        Raises:
            AdapterUnavailableError: If the capture will not open -- a camera index that
                is not present, a path that does not exist, an unreadable codec. The
                message names which of the two branches was taken, because "0" opening as
                a camera and ``./0`` opening as a file are different mistakes.
        """
        self._is_camera = source.isnumeric()
        self._clock = clock
        self._closed = False

        self._capture = cv2.VideoCapture(int(source) if self._is_camera else source)
        if not self._capture.isOpened():
            # Release before raising: a VideoCapture that failed to open still holds a
            # handle, and the caller has nothing to close because construction failed.
            self._capture.release()
            # Quoted by hand rather than with `!r`, because `repr` doubles every backslash
            # and this project's operators read Windows paths out of these messages.
            described = f'camera index {source}' if self._is_camera else f'video source "{source}"'
            raise AdapterUnavailableError(
                f"cannot open {described}. A source of all digits is read as a camera index "
                "and anything else as a path or URL, which is how the original read it. "
                "Check that the device is present and not held by another process, or that "
                "the path exists and its codec is one this OpenCV build supports."
            )

        self._timestamp: Callable[[], int] = self._clock if self._is_camera else self._media_time

    def __iter__(self) -> Iterator[Frame]:
        """Yield frames until the source is exhausted.

        A failed read ends the iteration rather than raising: for a file that is the end
        of the clip, and for a camera it is the device going away, which the pipeline
        treats as the end of the run and shuts down cleanly through its ``finally``.
        Neither is distinguishable from the other through this API, and neither is worth
        an exception the loop would only translate back into "stop".
        """
        index = 0
        while True:
            read, image = self._capture.read()
            if not read:
                return
            yield Frame(image=image, timestamp_ms=self._timestamp(), index=index)
            index += 1

    def close(self) -> None:
        """Release the capture. Idempotent, because the pipeline's ``finally`` may run
        alongside a signal handler that already closed it."""
        if self._closed:
            return
        self._closed = True
        self._capture.release()

    def _media_time(self) -> int:
        """The position, in whole milliseconds, of the frame just read.

        Read *after* ``read()`` and not before, which is the half of this that is easy to
        get wrong: with the FFMPEG backend ``CAP_PROP_POS_FRAMES`` after a read is the
        index of the *next* frame, while ``CAP_PROP_POS_MSEC`` is the presentation time of
        the frame just returned. Measured on this OpenCV build, a 10 fps clip stamps
        0, 100, 200, ... -- monotonic and starting at zero. Reading it before ``read()``
        yields the *previous* frame's time and would stamp the first two frames alike.

        Truncated rather than rounded, matching ``tools/capture_trace.py`` so a trace and
        a live replay of the same file agree to the millisecond.
        """
        return int(self._capture.get(cv2.CAP_PROP_POS_MSEC))


class UltralyticsPoseModel:
    """``YOLO("yolov8s-pose.pt")``, reduced to three index-aligned lists of floats.

    Isolates two things. The obvious one is torch: ``PoseDetection`` holds builtin floats,
    so every rule and every test downstream is free of tensors. The other is the *pairing*
    that the whole confidence story rests on -- ``boxes.conf[i]`` belongs to the person
    whose joints are ``keypoints[i]`` -- which is asserted here, at the seam, rather than
    assumed by five callers.

    That pairing was verified against ultralytics 8.3.253 rather than taken on trust: on
    ``bus.jpg`` (four people) and ``zidane.jpg`` (two), every person's confident keypoints
    fall inside the box at their own index and outside all the others.
    ``tests/integration/test_models.py`` keeps that evidence executable, because a
    silently reordered box would put one worker's confidence on another's gesture and
    nothing downstream could tell.

    **One upstream behaviour has changed since this project was written, and it moves the
    weight of a safety rule.** 8.0.x zeroed the coordinates of any keypoint whose
    confidence fell below 0.5, which is where the ``(0, 0)`` "not found" marker that
    ``draw_plan``, ``geometry`` and ``PoseDetection`` all describe comes from -- and
    ``Keypoints.__init__`` still documents it. 8.3.253 does not: an unsure joint arrives at
    a plausible pixel position with a low confidence beside it. Nothing breaks, because
    every rule that measures an angle is gated on ``keypoint_visibility`` first, but that
    gate is now the *only* thing standing between a guessed elbow and a published
    FRONT_BEND. The sentinel checks are a second line of defence that this version rarely
    reaches, not the first one they read as.
    """

    def __init__(self, model: Any, *, confidence: float) -> None:
        """Wrap an already-loaded model.

        ``model`` is anything callable as ``model(image, conf=..., verbose=...)`` that
        returns a sequence of results; taking it as an argument rather than building it is
        what lets the conversion below be tested against a hand-built result object.
        Annotated ``Any`` for the reason ``KafkaEventPublisher`` annotates its producer so:
        naming the real class here, even under ``TYPE_CHECKING``, would put ultralytics
        back at module scope for every type checker and every reader who copies it.

        ``confidence`` is the detection gate, ``conf=0.8`` at line 291 of the original and
        ``thresholds.pose_confidence`` in the configuration.
        """
        self._model = model
        self._confidence = confidence
        self._warned_without_visibility = False

    @classmethod
    def load(cls, weights: Path, *, confidence: float) -> UltralyticsPoseModel:
        """Load pose weights from ``weights``.

        Raises:
            AdapterUnavailableError: If ultralytics is not installed, the file is not
                there, or the weights will not load.
        """
        return cls(model=_load_yolo(weights, "pose"), confidence=confidence)

    def __call__(self, image: Any) -> PoseDetection:
        """Run the pose model on one frame and convert its output.

        Called exactly as the original called it -- ``model(frame, conf=...)``, line 291 --
        with one addition: ``verbose=False``. The original let ultralytics print a line per
        frame to stdout, which at 25 fps is a log nobody can read and a stream nobody can
        redirect; this package logs through ``logging``.

        A frame the model found nobody in returns three empty lists, and that is a normal
        answer rather than a special case: ``pipeline`` runs every stage on it anyway. In
        8.3 that frame arrives as ``keypoints.data`` of shape ``(0, 17, 3)`` and
        ``keypoints.conf`` of shape ``(0, 17)`` -- an empty *batch* of full-width rows, so
        ``keypoints`` is not None and the original's ``keypoints.shape[1] == 0`` guard
        (line 301) reads 17, is false, and lets the frame through to a crash three lines
        later. Pinned by
        ``test_models.py::test_a_person_free_frame_is_an_empty_batch_of_full_width_rows``.

        Raises:
            ValueError: If the three rows are not the same length, which would mean the
                library stopped pairing boxes with keypoints by index. Loud here rather
                than silent downstream: the pipeline zips them strictly, so the same
                mistake would otherwise surface as a per-frame traceback naming neither
                the model nor the assumption it broke.
        """
        result = self._model(image, conf=self._confidence, verbose=False)[0]

        keypoints = getattr(result, "keypoints", None)
        boxes = getattr(result, "boxes", None)

        # `.tolist()` once, and everything after it is builtin floats. Reading the tensor
        # element by element would be both slower and a way for a torch scalar to escape.
        rows = [] if keypoints is None else keypoints.data.tolist()
        keypoints_xy = [[(float(row[0]), float(row[1])) for row in person] for person in rows]
        keypoint_conf = self._visibility(keypoints, rows)
        box_conf = [] if boxes is None else [float(value) for value in boxes.conf.tolist()]

        if not len(keypoints_xy) == len(keypoint_conf) == len(box_conf):
            raise ValueError(
                f"the pose model returned {len(keypoints_xy)} keypoint rows, "
                f"{len(keypoint_conf)} visibility rows and {len(box_conf)} box "
                "confidences for one frame. The three are one row per person and are "
                "paired by index -- box_conf[i] is the confidence of the person whose "
                "joints are keypoints_xy[i] -- and every gesture event publishes that "
                "pairing as its confidencePercentage."
            )

        return PoseDetection(
            keypoints_xy=keypoints_xy,
            keypoint_conf=keypoint_conf,
            box_conf=box_conf,
        )

    def _visibility(self, keypoints: Any, rows: list[list[list[float]]]) -> list[list[float]]:
        """Per-keypoint visibility scores, one row per person.

        ``Keypoints.conf`` is the third column of ``data`` when the weights report one and
        ``None`` when they do not (``has_visible = data.shape[-1] == 3``). Weights without
        it are not a crash and not a silent zero: a zero would fail every visibility gate
        and the detector would report nothing at all, for ever, without a word. They are
        treated as fully visible and warned about once, because that is the only reading
        under which the gates are merely absent rather than inverted.
        """
        conf = None if keypoints is None else keypoints.conf
        if conf is not None:
            return [[float(value) for value in person] for person in conf.tolist()]

        if rows and not self._warned_without_visibility:
            self._warned_without_visibility = True
            _LOGGER.warning(
                "the pose weights report no per-keypoint visibility (each keypoint has "
                "%d columns, not 3), so every visibility gate is treated as passed and "
                "gestures may be measured from joints the model never found. This is "
                "reported once per run.",
                len(rows[0][0]) if rows[0] else 0,
            )
        return [[1.0] * len(person) for person in rows]


class UltralyticsObjectModel:
    """``YOLO("best.pt")``, reduced to one plain record per PPE or fall box.

    Isolates the model's *vocabulary* as well as its tensors. ``results.names`` maps a
    float class index to a string, and this is the only place that mapping is read;
    ``pipeline`` then translates the string into an ``EventType`` in its own single place.
    The original did both inline, comparing ``names[int(cls)]`` against three string
    literals at five separate sites.
    """

    def __init__(self, model: Any, *, confidence: float) -> None:
        """Wrap an already-loaded model.

        ``model`` is anything with ``predict(image, show=..., conf=..., verbose=...)``.
        ``confidence`` is the original's ``conf=0.6`` (line 293), configured as
        ``thresholds.ppe_confidence``.
        """
        self._model = model
        self._confidence = confidence

    @classmethod
    def load(cls, weights: Path, *, confidence: float) -> UltralyticsObjectModel:
        """Load PPE/fall weights from ``weights``.

        Raises:
            AdapterUnavailableError: If ultralytics is not installed, the file is not
                there, or the weights will not load.
        """
        return cls(model=_load_yolo(weights, "PPE"), confidence=confidence)

    def __call__(self, image: Any) -> Sequence[ObjectDetection]:
        """Run the PPE/fall model on one frame and convert every box it drew.

        Called as the original called it -- ``predict(frame, show=False, conf=...)``, line
        293 -- plus ``verbose=False``, for the reason given on the pose model.

        Every box is returned, including classes this detector has no event for. Filtering
        belongs to ``pipeline._EVENT_TYPE_BY_LABEL``, which already ignores an unmapped
        label, and the sink draws the boxes it is given -- so dropping one here would make
        the overlay disagree with what the model saw.

        The three tensors are zipped strictly. They are three columns of one table and
        cannot differ in length; if they ever do, the frame is abandoned with a message
        rather than a box silently taking its neighbour's confidence.
        """
        result = self._model.predict(image, show=False, conf=self._confidence, verbose=False)[0]

        boxes = getattr(result, "boxes", None)
        if boxes is None:
            # A model with no detection head at all. Not an error: an empty frame is a
            # valid observation and the pipeline handles it like any other.
            return ()

        names = getattr(result, "names", {})
        detections: list[ObjectDetection] = []
        for box, class_index, confidence in zip(
            boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist(), strict=True
        ):
            x1, y1, x2, y2 = box
            detections.append(
                ObjectDetection(
                    label=_label_of(names, int(class_index)),
                    confidence=float(confidence),
                    box=(int(x1), int(y1), int(x2), int(y2)),
                )
            )
        return detections


class AnnotatingSink:
    """Draws one frame's detections and writes the preview the web app polls.

    **Written through a temporary file and ``os.replace``, never onto the target.** This
    is the defect it exists to fix. The original wrote ``cv2.imwrite('output_image.jpg')``
    straight onto the served path (line 525), every frame, while the engine's
    ``EventController.getImage`` serves that same single file and ``VideoStream.js`` polls
    it every 100 ms. An encode is not atomic: the reader that arrives mid-write gets a
    truncated JPEG, which the browser renders as a grey band or drops entirely, and at 25
    frames a second the window is open a quarter of the time. Encoding to memory, writing
    the whole of it to a sibling temporary file and then renaming closes it: ``os.replace``
    is atomic within a directory on both POSIX and Windows, so a reader sees either the
    previous frame whole or the new frame whole, and never half of either.

    The temporary file is named for this process, so two detectors sharing an output
    directory cannot overwrite each other's half-written frame, and there is at most one
    stray per process if it is killed mid-write. ``close`` removes it.

    **The rename can be refused, and that is not a lost frame.** Windows fails a rename
    over a file another process currently has open -- exactly what the engine is doing to
    this one, ten times a second -- with ``PermissionError``. It is retried for a few
    milliseconds and then given up on, leaving the previous frame in place: the next frame
    is 40 ms away, so a preview one frame stale is invisible, whereas raising would cost a
    traceback per frame for as long as a browser tab stayed open. ``skipped_count`` carries
    the total. This is deliberately gentler than ``KafkaEventPublisher``, which logs every
    single drop, and the difference is what is at stake: a dropped event is a safety
    incident nobody will ever know about, while a dropped preview frame is one twenty-fifth
    of a second of video.

    Isolating the write here has a second consequence worth stating: this is the only
    place a frame's pixels are read at all. ``Frame.image`` is opaque to ``pipeline``, and
    it is opaque precisely so that the sink can be swapped for one that writes nothing.
    """

    def __init__(
        self, target: Path, *, max_dimension: int | None = _DEFAULT_MAX_DIMENSION
    ) -> None:
        """Prepare to write annotated frames to ``target``.

        ``target``'s suffix chooses the encoder -- ``.jpg`` for the engine, which serves
        it as ``image/jpeg`` -- and its parent directory is created if it is missing, so a
        misconfigured path fails now rather than on the first frame of a night shift.

        ``max_dimension`` scales the written image so its longest side is that many
        pixels, which is the original's ``scale = 640 / max(h, w)`` (line 519) and matters
        because the browser re-fetches this file ten times a second. It is applied in both
        directions, as the original applied it: a frame smaller than 640 is enlarged.
        ``None`` writes the frame at its own size.

        Raises:
            AdapterUnavailableError: If ``target`` has no suffix, if its directory cannot
                be created, or if ultralytics -- whose ``Annotator`` supplies the skeleton
                table and the palettes this sink draws with -- is not installed.
        """
        if not target.suffix:
            raise AdapterUnavailableError(
                f'the annotated frame path "{target}" has no file extension. OpenCV '
                "chooses its image encoder from the extension, so a path without one "
                "cannot be written at all. Use something like 'output_image.jpg'."
            )

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AdapterUnavailableError(
                f'cannot create the directory for the annotated frame "{target}": '
                f"{type(exc).__name__}: {exc}"
            ) from exc

        try:
            from worksite_detector.annotate import PlanAnnotator
        except ImportError as exc:
            raise AdapterUnavailableError(
                "the pose overlay needs ultralytics, whose Annotator supplies the COCO "
                f"skeleton table and the keypoint palettes: {_INSTALL_HINT}. Alternatively "
                "configure `output.write_annotated_frame: false` and use a sink that "
                "writes nothing."
            ) from exc

        self._annotator_factory: Callable[[Any], Any] = PlanAnnotator
        self._target = target
        self._suffix = target.suffix
        # One fixed name per process rather than a fresh mkstemp per frame: a crash then
        # leaves at most one stray file instead of one per frame, and it is in the same
        # directory as the target, which is what makes the rename atomic.
        self._temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        self._max_dimension = max_dimension
        #: How many frames a reader held the target through. Mutable and unsynchronised,
        #: matching the single-threaded frame loop that owns it, and reported at shutdown.
        self.skipped_count: int = 0

    def write(self, frame: Frame, pose: PoseDetection, objects: Sequence[ObjectDetection]) -> None:
        """Annotate one frame and replace the target with it.

        Draws onto a copy: ``Annotator`` mutates the array it is given, and ``frame.image``
        belongs to the capture that produced it.

        Skeletons first and violation boxes over them, which is the original's order (401,
        then 456) and the one that matters -- a box is a claim about a region and must not
        be hidden under a limb. People are drawn in model order, so the person drawn last
        is the one with the highest positional id, which is the id the pipeline gives the
        gesture detector.

        Every frame is written, including one with nobody and nothing in it. That is the
        frozen-preview defect: the original's ``continue`` at line 310 skipped the write on
        person-free frames, so an operator watching an empty site saw a still picture with
        nothing to distinguish it from a dead camera.

        A rename the operating system refuses -- because a reader has the target open --
        is counted rather than raised; see the class docstring.

        Raises:
            RuntimeError: If OpenCV cannot encode the frame. The pipeline abandons that
                one frame and carries on; the previous preview stays in place, whole.
        """
        image = frame.image.copy()
        height, width = image.shape[:2]
        size_ratio = max(
            width / _OVERLAY_REFERENCE_WIDTH, height / _OVERLAY_REFERENCE_HEIGHT
        )

        annotator = self._annotator_factory(image)
        for keypoints_xy, keypoint_conf in zip(
            pose.keypoints_xy, pose.keypoint_conf, strict=True
        ):
            # (x, y, visibility) rows, the shape `Annotator.kpts` and `draw_plan` both
            # take. The two lists are index-aligned by `PoseDetection`'s contract, and
            # zipping them strictly is what proves it on every frame.
            annotator.kpts(
                [(x, y, conf) for (x, y), conf in zip(keypoints_xy, keypoint_conf, strict=True)],
                shape=(height, width),
                size_ratio=size_ratio,
            )

        annotated = annotator.result()
        for detection in objects:
            _draw_violation_box(annotated, detection)

        self._replace_target(_resized(annotated, self._max_dimension))

    def close(self) -> None:
        """Remove this process's temporary file if one survived a failed write.

        The target itself is left exactly as it is: it is the last frame the operator saw,
        and deleting it on shutdown would turn a stopped detector into a broken image.
        Idempotent.
        """
        self._temporary.unlink(missing_ok=True)

    def _replace_target(self, image: Any) -> None:
        """Encode to memory, write the whole of it, then rename over the target.

        Encoding first, and entirely in memory, is what makes the write atomic: nothing on
        disk is touched until there is a complete image to put there, so a failure costs
        the operator nothing but the newest frame.
        """
        encoded, buffer = cv2.imencode(self._suffix, image)
        if not encoded:
            raise RuntimeError(
                f"OpenCV could not encode the annotated frame as {self._suffix!r}. The "
                "extension of the configured output path chooses the encoder, and this "
                "build has none for that one."
            )
        self._temporary.write_bytes(buffer.tobytes())

        for remaining in reversed(range(_REPLACE_ATTEMPTS)):
            try:
                os.replace(self._temporary, self._target)
                return
            except PermissionError:
                # Windows refuses to rename over a file another process has open, which is
                # what the engine does to this one on every poll. It lets go in
                # microseconds, so a few short waits clear almost all of them.
                if remaining:
                    time.sleep(_REPLACE_BACKOFF_SECONDS)

        self.skipped_count += 1
        # The first one is worth an operator's attention -- it can also mean the file is
        # held open permanently, by an editor or a virus scanner, in which case the preview
        # is frozen for good. After that it is noise: every subsequent frame would say the
        # same thing, and `skipped_count` already has the number.
        _LOGGER.log(
            logging.WARNING if self.skipped_count == 1 else logging.DEBUG,
            'could not replace the annotated frame "%s" after %d attempts: a reader is '
            "holding it open. The previous frame stays in place and the preview is one "
            "frame stale; %d frames have been skipped this way so far.",
            self._target,
            _REPLACE_ATTEMPTS,
            self.skipped_count,
        )


def _draw_violation_box(image: Any, detection: ObjectDetection) -> None:
    """One green rectangle and its raw model label, as the original drew them.

    The label is the model's class -- ``no-helmet``, not ``NO_HELMET`` -- on purpose: the
    overlay shows what the model saw, and the translation into the engine's vocabulary is
    a decision made once, in ``pipeline``.
    """
    x1, y1, x2, y2 = detection.box
    cv2.rectangle(image, (x1, y1), (x2, y2), _BOX_COLOR, _BOX_THICKNESS)
    cv2.putText(
        image,
        detection.label,
        (x1, y1),
        cv2.FONT_HERSHEY_SIMPLEX,
        _LABEL_SCALE,
        _LABEL_COLOR,
        _LABEL_THICKNESS,
        cv2.LINE_AA,
    )


def _resized(image: Any, max_dimension: int | None) -> Any:
    """The image scaled so its longest side is ``max_dimension``, or unchanged."""
    if max_dimension is None:
        return image
    scale = max_dimension / max(image.shape[0], image.shape[1])
    return cv2.resize(image, (0, 0), fx=scale, fy=scale)


def _label_of(names: Any, class_index: int) -> str:
    """The model's name for a class index, or the index itself if it has none.

    ``Results.names`` is a dict keyed by int in every ultralytics version this project
    supports, but a model shipped with an incomplete table must not stop a safety
    detector: an unnamed class becomes the string of its index, which maps to no event and
    is ignored -- the same answer ``pipeline`` already gives an unknown label.
    """
    try:
        return str(names[class_index])
    except (KeyError, IndexError, TypeError):
        _LOGGER.warning(
            "the model reported class index %d, which its names table does not name; "
            "the detection is kept as %r and will match no event type",
            class_index,
            str(class_index),
        )
        return str(class_index)


def _load_yolo(weights: Path, kind: str) -> Any:
    """Load one set of YOLO weights, or say precisely why it could not.

    The existence check is not redundant with what ultralytics does. ``YOLO("best.pt")``
    on a missing file **downloads** a model whose name it recognises, so a mistyped path
    can silently start a network fetch and then run a detector on weights nobody chose.
    ``ModelConfig`` deliberately resolves and opens nothing at load time; this is the
    moment the path stops being a string of intent, and the check belongs here.
    """
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise AdapterUnavailableError(
            f"the {kind} model needs the ultralytics package, which is not installed: "
            f"{_INSTALL_HINT}."
        ) from exc

    if not weights.is_file():
        raise AdapterUnavailableError(
            f'the {kind} weights are not at "{weights}". Relative paths resolve '
            f"against the working directory, which is currently {Path.cwd()}. The file is "
            "not fetched for you: a name ultralytics recognises would otherwise be "
            "downloaded from the internet and silently run in place of the trained model."
        )

    try:
        return YOLO(str(weights))
    except Exception as exc:
        raise AdapterUnavailableError(
            f'could not load the {kind} weights at "{weights}": '
            f"{type(exc).__name__}: {exc}"
        ) from exc
