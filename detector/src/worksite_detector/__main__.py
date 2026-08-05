"""The composition root: the one module that turns tested parts into a program.

Every other module in this package takes its collaborators as arguments and its numbers
from a ``Config``. That is exactly what makes them testable on a laptop with no camera, no
weights and no broker -- and it is also why not one of them can start. Something has to
read the command line, resolve the configuration, check that the weights are on disk, open
the camera, load two models, choose a publisher, wire eleven collaborators into a
``Pipeline`` and decide what the process exits with. This is that something, and it owns
four things nothing else in the package is allowed to touch:

* **The inputs of the process.** ``sys.argv`` and the environment are read here and nowhere
  else. ``load_config`` takes its environment as a parameter precisely so that no module
  below can reach for ``os.environ`` behind a test's back; ``main`` takes one too, for the
  same reason and from the same distance.
* **The filesystem, before a frame is read.** ``load_config`` deliberately resolves nothing
  and opens nothing, so a workstation can edit a config naming paths only the detector host
  can see. Somebody still has to say "that file is not there" *before* ultralytics says it
  from six frames deep -- see ``require_weights``.
* **Process-wide state**: the logging configuration and the ``SIGINT``/``SIGTERM``
  handlers. A library that calls ``basicConfig`` or installs a signal handler has decided
  something on behalf of a program it cannot see. This module is the program.
* **The exit code.** 0 for a clean shutdown, 2 for a configuration that cannot be resolved,
  3 for a resource a valid configuration named but that could not be opened -- a camera, a
  broker, weights, a missing CV stack. Startup failures are printed to stderr as a sentence
  and never as a traceback: the operator caused them and can fix them, and a traceback out
  of the middle of ultralytics tells them nothing about which of a dozen settings is wrong.

**What ``aiModule.py`` got wrong at exactly this seam**, and what each fix costs to keep:

* ``parse_args()`` is defined at line 187 and **never called**. Every setting comes from the
  two hardcoded ``Args`` classes below it instead, which differ only in which gesture name
  they carry, so nothing at all is configurable without editing Python -- and its
  ``--sport`` default, ``'squat'``, is not even a key in that file's gesture table. An
  argument parser nobody calls is worse than none: it documents flags that do nothing.
* ``cv2.imshow`` is commented out at line 526 while ``cv2.waitKey(1) & 0xFF == ord("q")``
  survives at 529. There is no window to receive the keypress, so the documented way to
  quit does nothing, and the only way out is killing the process -- which skips the release
  of the capture, the flush of any PPE window still open, and ``producer.close()``, all of
  which sit *after* the loop. A detector that can only be stopped by ``SIGKILL`` loses its
  last violation every single time it is stopped. That is what ``ShutdownFlag`` and the two
  signal handlers exist for, and why the flag is read *between* frames rather than aborting
  one: a half-processed frame is a published FALL that never reaches the broker.
* The Kafka producer is built at **module scope** (line 16), so the file cannot be imported
  without a broker -- not by a test, not by ``--help``, not by a linter. Here the choice of
  publisher is a function of one flag, and ``--dry-run`` picks ``InMemoryEventPublisher``,
  which is the whole point of that flag: the entire pipeline runs, end to end, on a machine
  with nothing installed and nothing listening, and prints what it would have sent.

**The command line is layered *through* ``load_config``, not on top of it.** Defaults, then
the YAML file, then the environment is a merge that module already implements, leaf by
leaf, with type coercion and an error naming any key it does not recognise. A fourth merge
written here would be a second implementation of the same rules, and it would drift.
Instead ``--source`` and ``--no-display`` are spelled as the ``WSM_`` variables they are
equivalent to and handed to ``load_config`` as part of the environment mapping, so a flag
is coerced, validated and reported exactly like the setting it overrides. The order that
falls out -- defaults < file < environment < command line -- is the intended one: a person
typing a flag is making the most specific statement of intent in the room.

One consequence of passing the real environment through: a stray ``WSM_``-prefixed variable
that names no setting is fatal at startup, by ``load_config``'s design. That is the point of
it. ``WSM_KAFKA__BOOTSTRAP_SERVER``, singular, is an operator who believes they redirected
the detector and did not.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path
from types import FrameType
from typing import Any, Final, NamedTuple, TextIO

from worksite_detector.config import Config, load_config
from worksite_detector.events import DetectionEvent, EventType
from worksite_detector.pipeline import Frame, ObjectDetection, Pipeline, PoseDetection
from worksite_detector.pose_rules import GestureDetector
from worksite_detector.ppe_rules import FallThrottle, PpeViolationTracker
from worksite_detector.publisher import (
    EventPublisher,
    InMemoryEventPublisher,
    KafkaEventPublisher,
)

# Spelled out rather than taken from `__name__`, which is the one module in this package
# where that would be wrong: under `python -m worksite_detector` the interpreter rebinds
# `__name__` to "__main__", so the root's records would be filed under a name that changes
# with how the program was launched -- and would sit outside the `worksite_detector`
# hierarchy an operator raises or silences.
_LOGGER = logging.getLogger("worksite_detector.__main__")

#: How the program names itself in an error message. The same string as the console script
#: in `pyproject.toml`, so a message can be pasted straight back into a shell.
_PROGRAM: Final = "worksite-detector"

#: Where the two sets of weights come from. `best.pt` is 50 MB of trained model and is
#: gitignored, so "clone and run" cannot work without this line being somewhere an operator
#: meets at the moment it matters.
#:
#: One specific tag, not `/releases` and not `/releases/latest`. The weights are attached to
#: a *pre-release* on purpose -- it carries assets, not a version of this code -- and GitHub
#: resolves `/releases/latest` only to a full release, so that URL 404s while `weights-v1`
#: is the only thing published. A tag URL is exact today and stays correct on the day a code
#: release is cut beside it.
_WEIGHTS_RELEASE_URL: Final = (
    "https://github.com/worksite-safety/worksite-safety-monitor/releases/tag/weights-v1"
)

EXIT_OK: Final = 0
#: The configuration cannot be resolved: bad YAML, an unknown key, a value of the wrong
#: type, a `--config` path that is not there. 2 is also what argparse exits with on an
#: unknown flag, which is the same class of mistake made one layer earlier.
EXIT_CONFIGURATION: Final = 2
#: The configuration is valid but something it names could not be opened: the camera, the
#: broker, the weights, or an optional dependency. Distinct from 2 because the fix is
#: somewhere else entirely -- the rig, not the file.
EXIT_UNAVAILABLE: Final = 3
#: Interrupted before the frame loop began, where a stop flag has nothing to stop.
#: 128 + SIGINT, the shell convention.
EXIT_INTERRUPTED: Final = 130


class StartupError(RuntimeError):
    """The detector cannot start, and the message says what to do about it.

    A ``RuntimeError`` so that it is caught by the same clause as
    ``AdapterUnavailableError`` and ``PublisherUnavailableError``: all three mean "a
    resource a valid configuration named is not usable", all three are raised during
    startup, and the response to each is identical -- print the sentence, do not start.
    """


class ShutdownFlag:
    """A stop request, set by a signal and read between frames.

    One bool with two names for its two sides of the seam: ``request_stop`` is what a
    signal handler calls, ``should_stop`` is what ``Pipeline`` polls before each frame. It
    is deliberately *not* an abort. The pipeline finishes the frame it is on, publishes
    whatever that frame produced, then runs its shutdown path -- flushing the PPE windows
    still open and closing the source, the sink and the publisher. The original had no such
    path at all: its documented quit key had no window to be pressed in, so the only exit
    was killing the process, and everything after its loop -- the capture release, the
    producer close -- was dead code.

    The delay that costs is one frame plus one blocking read from the source: a stop that
    arrives while the camera is mid-read is noticed when that read returns. A camera that
    has stopped producing frames entirely will not notice at all, which is the one case
    where a second signal is the operator's answer.

    Not thread-safe and not required to be. A Python signal handler runs in the main thread
    between bytecodes, and the pipeline reads the flag from that same thread.
    """

    def __init__(self) -> None:
        """Start clear: nothing has asked the detector to stop."""
        self._requested = False

    def request_stop(self, reason: str) -> None:
        """Ask the frame loop to stop after the frame it is on.

        Idempotent by nature -- the flag is already set -- but a repeat is worth its own
        record, because it is an operator pressing Ctrl+C a second time and wondering why
        nothing has happened yet. ``reason`` names what asked, so a ``SIGTERM`` from an
        orchestrator is distinguishable in the log from a ``SIGINT`` at a keyboard.

        Reached from a signal handler, where ``logging`` is safe for the reason it is safe
        anywhere: its lock is a re-entrant lock held by this same thread.
        """
        if self._requested:
            _LOGGER.warning(
                "%s again: a stop is already in progress and the current frame has to "
                "finish, or the events it has already detected are lost. If the camera "
                "has stopped producing frames entirely, kill the process.",
                reason,
            )
            return

        self._requested = True
        _LOGGER.info(
            "%s: stopping after the current frame. Any PPE violation still open will be "
            "flushed and published, and the camera, preview and publisher closed.",
            reason,
        )

    def should_stop(self) -> bool:
        """Whether a stop has been requested. This is what ``Pipeline`` is handed."""
        return self._requested


class DiscardingSink:
    """The sink for a run that writes no preview at all.

    ``output.write_annotated_frame: false`` -- and its command-line spelling
    ``--no-display`` -- is a setting with no implementation anywhere else: ``AnnotatingSink``
    always writes, and says so, pointing at "a sink that writes nothing" as the caller's to
    supply. This is that sink, and it lives here because choosing between two
    implementations of one protocol from one config flag is the composition root's entire
    job description.

    It is not a no-op for free. Skipping the write skips the annotate, the JPEG encode and
    the disk replace, which is most of the per-frame cost that is not a model; a headless
    site pays none of it, and the web app's stream page shows nothing.
    """

    def write(
        self, frame: Frame, pose: PoseDetection, objects: Sequence[ObjectDetection]
    ) -> None:
        """Discard one frame's annotations. The frame itself is never touched."""

    def close(self) -> None:
        """Nothing is held, so nothing is released. Idempotent."""


class Wiring(NamedTuple):
    """A built detector, and the two collaborators whose counters are reported at exit.

    ``KafkaEventPublisher.dropped_count`` and ``AnnotatingSink.skipped_count`` are both
    documented as "reported at shutdown", and neither the publisher nor the sink nor the
    pipeline reports them -- each counts, and the composition root is the only thing that
    still exists once the run is over and can say the number out loud.
    """

    pipeline: Pipeline
    publisher: EventPublisher
    sink: Any


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Read the command line into a namespace of four settings.

    ``argv`` is the argument list without the program name, or None for ``sys.argv[1:]``.
    Taking it as a parameter is what lets the parser be tested at all -- the original's
    equivalent read ``sys.argv`` directly, and was then never called from anywhere.

    Every flag here overrides a configuration setting rather than introducing one, so there
    is exactly one place each value is documented, validated and defaulted:
    ``config.py``. ``--source`` is ``camera.source``, ``--no-display`` is
    ``output.write_annotated_frame``, and both are handed to ``load_config`` as the
    ``WSM_`` variables they are equivalent to.
    """
    parser = argparse.ArgumentParser(
        prog=_PROGRAM,
        description=(
            "Watch a camera or video file for PPE violations, falls and gestures, and "
            "publish them to the engine's Kafka topic."
        ),
        epilog=(
            "Start with --dry-run: it runs the whole pipeline, contacts no broker, needs "
            "no Kafka client library, and prints a summary of what it would have "
            "published. Every setting can also be given in a YAML file (--config) or as "
            "WSM_<SECTION>__<FIELD> in the environment; see config.example.yaml."
        ),
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        type=Path,
        default=None,
        help=(
            "YAML configuration file. Settings it does not mention keep their defaults; "
            "a key it invents is an error naming the key. Omit it to run on defaults."
        ),
    )
    parser.add_argument(
        "--source",
        metavar="SOURCE",
        default=None,
        help=(
            "What to watch: a webcam index ('0'), a video file path, or a stream URL. "
            "Overrides camera.source. Note that a camera with no configured name is "
            "named after its source, so this also labels the events it produces."
        ),
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help=(
            "Do not write the annotated preview frame the web app polls, skipping the "
            "encode and the disk write on every frame. Overrides "
            "output.write_annotated_frame; there is no opposite flag, because leaving "
            "this off means 'whatever the configuration says'."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Collect events in memory instead of publishing them, and print a summary at "
            "exit. Nothing is sent anywhere and no broker is contacted."
        ),
    )
    return parser.parse_args(argv)


def resolve_config(args: argparse.Namespace, env: Mapping[str, str]) -> Config:
    """Resolve defaults, then the file, then the environment, then the command line.

    The last layer is the only one added here, and it is added *as* an environment mapping
    rather than as a fourth merge: ``load_config`` already coerces, validates and reports
    every leaf, and a flag deserves the same treatment as the setting it overrides. See
    the module docstring for why the command line sits on top of the environment.

    Raises:
        ValueError: If any layer names a section or setting that does not exist, holds a
            value of the wrong type, or breaks one of ``Config``'s invariants.
        FileNotFoundError: If ``--config`` names a file that is not there.
    """
    overrides: dict[str, str] = {}
    if args.source is not None:
        overrides["WSM_CAMERA__SOURCE"] = args.source
    if args.no_display:
        overrides["WSM_OUTPUT__WRITE_ANNOTATED_FRAME"] = "false"

    return load_config(args.config, {**env, **overrides})


def require_weights(config: Config) -> None:
    """Refuse to start when either set of weights is missing, and say where to get them.

    This is the check that decides a new user's first experience. ``load_config``
    deliberately touches no filesystem, and ``adapters._load_yolo`` checks one file at a
    time from inside a model load -- by which point the operator has already waited for
    torch to import. Both files are checked here, together, before anything heavy is
    imported at all, so "I cloned it and it does not run" is answered by one sentence
    naming both missing files and the release they are attached to.

    Raises:
        StartupError: If either path does not name an existing file.
    """
    missing = [
        (label, path)
        for label, path in (
            ("pose", config.models.pose_weights),
            ("PPE/fall", config.models.ppe_weights),
        )
        if not path.is_file()
    ]
    if not missing:
        return

    # Quoted by hand rather than with `!r`, matching `adapters`: `repr` doubles every
    # backslash and this project's operators read Windows paths out of these messages.
    named = " and ".join(f'the {label} weights are not at "{path}"' for label, path in missing)

    # The `--dir` of the suggested command is *resolved*, not the literal "detector/models"
    # -- a relative example would be wrong from the one directory the operator is most
    # likely standing in when they read this. `python -m worksite_detector` is documented
    # as being run from `detector/`, where "detector/models" names `detector/detector/models`.
    # When both files are configured into one directory (the default, and every
    # configuration anyone has written) a single command fetches both; when they are not,
    # no one command can, and the paths above are already the instruction.
    directories = {path.parent for _, path in missing}
    if len(directories) == 1:
        target = directories.pop().resolve()
        how = (
            "fetch both with `gh release download weights-v1 --repo "
            f'worksite-safety/worksite-safety-monitor --pattern \'*.pt\' --dir "{target}"`, '
            f"or download them from that page into {target}"
        )
    else:
        how = "download them from that page to exactly the paths named above"

    raise StartupError(
        f"{named}. Relative paths resolve against the working directory, which is "
        f"currently {Path.cwd()}. Both files are attached to the weights-v1 release at "
        f"{_WEIGHTS_RELEASE_URL}: {how}, or point models.pose_weights and "
        "models.ppe_weights at wherever you keep them. They are not fetched for you -- "
        "ultralytics downloads any weights name it recognises, so a mistyped path would "
        "otherwise start a silent network fetch and run a stock model in place of the one "
        "this project trained."
    )


def build_publisher(config: Config, *, dry_run: bool) -> EventPublisher:
    """Choose where events go: memory under ``--dry-run``, Kafka otherwise.

    The one decision that makes this program demonstrable. ``InMemoryEventPublisher`` is
    production code rather than a test double, so ``--dry-run`` is the real pipeline with
    the real rules against a machine that has neither a broker nor the client library --
    the case the original could not even be imported in.

    Raises:
        PublisherUnavailableError: If the Kafka branch is taken and the client library is
            missing or the broker cannot be reached. Never on the dry-run branch, which is
            what makes it the thing to suggest when the Kafka branch fails.
    """
    if dry_run:
        _LOGGER.info(
            "--dry-run: events will be collected in memory and summarised at exit; "
            "nothing will be published and no broker will be contacted"
        )
        return InMemoryEventPublisher()

    return KafkaEventPublisher.connect(
        bootstrap_servers=config.kafka.bootstrap_servers, topic=config.kafka.topic
    )


def build_sink(config: Config) -> Any:
    """Choose what happens to the annotated frame: written, or discarded.

    The ultralytics import that ``AnnotatingSink`` needs for its skeleton table lives
    behind this branch, so a run with the preview switched off never reaches for it.

    Raises:
        AdapterUnavailableError: If the preview is on and its path has no file extension,
            its directory cannot be created, or ultralytics is not installed.
    """
    if not config.output.write_annotated_frame:
        _LOGGER.info(
            "the annotated preview is switched off, so the web app's stream page will "
            "show nothing for this camera"
        )
        return DiscardingSink()

    from worksite_detector.adapters import AnnotatingSink

    return AnnotatingSink(config.output.annotated_frame_path)


def build_pipeline(
    config: Config, *, dry_run: bool, should_stop: Callable[[], bool]
) -> Wiring:
    """Open every real resource and wire the frame loop that uses them.

    The imports of ``adapters`` are inside this function, and that placement is load
    bearing twice over. ``tests/test_architecture.py`` does not exempt this module, so it
    may never name cv2, ultralytics, kafka or torch -- it names ``adapters``, which is the
    module that may. And deferring even that import is what lets ``--help``, a typo in a
    YAML file and a missing weights file all be answered on a machine with no CV stack
    installed, in milliseconds, rather than after a multi-second torch import.

    Collaborators are built cheapest-to-fail first -- publisher, preview, camera, then the
    two models -- so the most likely mistake is reported soonest, and everything already
    opened when a later step fails is closed on the way out. Once the ``Pipeline`` exists
    it owns those three and closes them in its own ``finally``, so the unwind here is
    dismissed rather than left to double-close them.

    Raises:
        AdapterUnavailableError: If the camera, the preview path or either set of weights
            cannot be opened, or the CV stack is not installed.
        PublisherUnavailableError: If a Kafka publisher was asked for and could not connect.
    """
    from worksite_detector.adapters import (
        OpenCvFrameSource,
        UltralyticsObjectModel,
        UltralyticsPoseModel,
    )

    # `CameraConfig.__post_init__` fills `name` from `source` when it is None, so the
    # fallback below is unreachable at runtime; it is spelled out because the declared type
    # is still `str | None` and `Pipeline` publishes this on every event as a `str`.
    camera_name = config.camera.name or config.camera.source

    with ExitStack() as stack:
        publisher = build_publisher(config, dry_run=dry_run)
        stack.callback(publisher.close)

        sink = build_sink(config)
        stack.callback(sink.close)

        source = OpenCvFrameSource(config.camera.source, clock=now_ms)
        stack.callback(source.close)

        pipeline = Pipeline(
            frame_source=source,
            pose_model=UltralyticsPoseModel.load(
                config.models.pose_weights, confidence=config.thresholds.pose_confidence
            ),
            object_model=UltralyticsObjectModel.load(
                config.models.ppe_weights, confidence=config.thresholds.ppe_confidence
            ),
            sink=sink,
            publisher=publisher,
            gesture_detector=GestureDetector(
                config.gestures,
                camera_name,
                keypoint_visibility=config.thresholds.keypoint_visibility,
                upright_left_idx=config.upright.left_idx,
                upright_right_idx=config.upright.right_idx,
                upright_angle=config.upright.angle_degrees,
            ),
            ppe_tracker=PpeViolationTracker(
                camera_name, grace_ms=config.thresholds.ppe_grace_ms
            ),
            fall_throttle=FallThrottle(config.thresholds.fall_cooldown_ms),
            # Read exactly once, by the shutdown flush: every event in the run is stamped
            # from the frame it was observed on, which is a decision `adapters` makes.
            clock=now_ms,
            should_stop=should_stop,
            camera_name=camera_name,
        )
        stack.pop_all()

    return Wiring(pipeline=pipeline, publisher=publisher, sink=sink)


def install_signal_handlers(flag: ShutdownFlag) -> None:
    """Make ``SIGINT`` and ``SIGTERM`` ask the frame loop to stop, rather than kill it.

    Both, because they are the two ways a detector is actually stopped and neither may skip
    the shutdown path: ``SIGINT`` is Ctrl+C at a terminal -- the exit the original
    documented with a ``waitKey`` that could never fire -- and ``SIGTERM`` is what an
    orchestrator sends before it stops waiting, which on a rig in a container is *every*
    stop. The default disposition of either kills the process outright, discarding whatever
    PPE window was open and whatever the client library still held buffered.

    Called immediately before the loop starts, not at startup. A flag nobody is polling yet
    would swallow a Ctrl+C during the several seconds torch takes to load and leave the
    operator with a process that ignores them.
    """

    def handle(signum: int, frame: FrameType | None) -> None:
        flag.request_stop(signal.Signals(signum).name)

    for received in (signal.SIGINT, signal.SIGTERM):
        signal.signal(received, handle)


def dry_run_summary(events: Sequence[DetectionEvent], config: Config) -> str:
    """The transcript of a dry run, as the block of text ``--dry-run`` prints.

    Built as a string rather than printed from inside, so what an operator sees is exactly
    what a test can assert. Types are listed in ``EventType`` declaration order rather than
    order of appearance, so two runs of the same footage produce comparable output.

    ``observed ms`` is the summed ``time_period_ms`` of the periodic types, which is the
    number the engine's ``/event/periodic-events`` chart sums; countable types have no
    duration at all and say so with a dash rather than a zero.
    """
    camera = config.camera.name or config.camera.source

    if not events:
        return (
            f'dry run finished: no events were collected from camera "{camera}".\n'
            "\n"
            "  Nothing cleared the thresholds. That is the ordinary result for a short\n"
            "  clip or an empty site: a pose detection has to clear "
            f"{config.thresholds.pose_confidence} and a PPE\n"
            f"  or fall detection {config.thresholds.ppe_confidence} before any rule sees "
            "it at all."
        )

    plural = "s" if len(events) != 1 else ""
    lines = [
        f'dry run finished: {len(events)} event{plural} collected from camera "{camera}", '
        "none published.",
        "",
        f"  {'event':<11}{'count':>5}{'first ms':>12}{'last ms':>12}{'observed ms':>14}",
    ]

    for event_type in EventType:
        matching = [event for event in events if event.event_type is event_type]
        if not matching:
            continue
        starts = [event.start_time_ms for event in matching]
        observed: int | str = "-"
        if event_type.is_periodic:
            observed = sum(event.time_period_ms or 0 for event in matching)
        lines.append(
            f"  {event_type.value:<11}{len(matching):>5}{min(starts):>12}"
            f"{max(starts):>12}{observed:>14}"
        )

    lines += [
        "",
        "Nothing was sent to a broker. Drop --dry-run to publish these to topic "
        f"{config.kafka.topic!r} at {config.kafka.bootstrap_servers}.",
    ]
    return "\n".join(lines)


def now_ms() -> int:
    """Milliseconds since the epoch, the unit every timestamp in this system is in.

    The only wall clock in the program. It stamps camera frames (a camera has no media
    position) and it is read once more at shutdown, to flush the PPE windows still open.
    """
    return int(time.time() * 1000)


def configure_logging() -> None:
    """Send the package's log records to stderr, at INFO.

    Here and nowhere else: a module that configures logging has decided the output format
    of a program it cannot see. stderr specifically, so that stdout carries only the
    dry-run summary and can be piped somewhere without a log record landing in the middle
    of it. The original printed one ultralytics progress line per frame to stdout, at 25
    frames a second, which is a stream nobody can read and nobody can separate.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        stream=sys.stderr,
    )


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Run one detector process and return its exit code.

    ``argv`` and ``env`` default to this process's own, and are parameters for the reason
    ``load_config`` takes an environment: a test states its whole world inline and cannot
    leak one run into the next through the process. ``stdout`` is where the dry-run summary
    goes, defaulting to the real one at call time rather than at import, so it follows a
    redirect.

    Returns ``EXIT_OK`` when the source is exhausted or a signal asked for a stop -- both
    are clean shutdowns, and both have run the flush. A startup failure returns
    ``EXIT_CONFIGURATION`` or ``EXIT_UNAVAILABLE`` with one sentence on stderr. Anything
    raised *during* the run is left to propagate as a traceback: the frame loop already
    survives a bad frame on its own, so what reaches here is a defect worth the frames, and
    the pipeline's ``finally`` has already closed everything either way.
    """
    args = parse_args(argv)
    configure_logging()
    flag = ShutdownFlag()

    try:
        config = resolve_config(args, os.environ if env is None else env)
    except (ValueError, FileNotFoundError) as exc:
        return _fail(exc, EXIT_CONFIGURATION)

    try:
        require_weights(config)
        wiring = build_pipeline(config, dry_run=args.dry_run, should_stop=flag.should_stop)
    except RuntimeError as exc:
        return _fail(exc, EXIT_UNAVAILABLE)
    except KeyboardInterrupt:
        # Ctrl+C during a multi-second model load, before there is a loop to ask to stop.
        # Reported as a sentence rather than as a traceback out of the middle of torch.
        return _fail("interrupted before the first frame was read", EXIT_INTERRUPTED)

    install_signal_handlers(flag)
    _LOGGER.info(
        "watching %s as camera %r; publishing %s",
        config.camera.source,
        config.camera.name or config.camera.source,
        "nothing (--dry-run)"
        if args.dry_run
        else f"to topic {config.kafka.topic!r} at {config.kafka.bootstrap_servers}",
    )

    wiring.pipeline.run()

    report_losses(wiring)
    if isinstance(wiring.publisher, InMemoryEventPublisher):
        print(dry_run_summary(wiring.publisher.events, config), file=stdout or sys.stdout)
    return EXIT_OK


def _fail(problem: object, code: int) -> int:
    """Print one sentence to stderr and return the exit code to leave with.

    The message is the exception's own, never a traceback: every startup failure in this
    program is raised with an actionable message by the layer that knows what went wrong,
    and a traceback would bury that message under frames from inside a library the operator
    did not write.
    """
    print(f"{_PROGRAM}: {problem}", file=sys.stderr)
    return code


def report_losses(wiring: Wiring) -> None:
    """Say out loud what the run lost, if anything.

    ``KafkaEventPublisher.dropped_count`` and ``AnnotatingSink.skipped_count`` are each
    documented as "reported at shutdown", and neither the publisher, the sink nor the
    pipeline reports them: they count, and the composition root is what is still standing
    when the run is over. Without this, a broker outage that swallowed a FALL leaves only
    per-event WARNINGs scrolled off the top of a log.

    Read with ``getattr`` because each counter belongs to one implementation of a
    two-method protocol -- ``InMemoryEventPublisher`` drops nothing and ``DiscardingSink``
    skips nothing, and neither should have to carry a counter to stay swappable. A run that
    lost nothing says nothing.
    """
    dropped = getattr(wiring.publisher, "dropped_count", 0)
    if dropped:
        _LOGGER.warning(
            "%d event(s) were detected but never reached the broker during this run. Each "
            "one was logged as it was dropped; a NO_HELMET or a FALL among them is a "
            "safety incident that no dashboard will ever show.",
            dropped,
        )

    skipped = getattr(wiring.sink, "skipped_count", 0)
    if skipped:
        _LOGGER.info(
            "%d preview frame(s) were skipped because a reader was holding the file open. "
            "That costs the web app a frame each time and nothing else; a large number "
            "means something holds the file permanently, such as an editor or a scanner.",
            skipped,
        )


if __name__ == "__main__":
    sys.exit(main())
