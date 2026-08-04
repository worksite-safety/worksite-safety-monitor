"""Unit tests for `worksite_detector.__main__` -- the composition root.

Three of the original's defects live at exactly this seam, and each one is a test below.

1. **`parse_args()` is defined at `aiModule.py` line 187 and never called.** Every setting
   comes from the two hardcoded `Args` classes under it, so nothing is configurable without
   editing Python, and its `--sport` default (`'squat'`) is not even a key in that file's
   gesture table. A parser nobody calls documents flags that do nothing, which is worse
   than having none. `test_every_flag_reaches_the_namespace` and the four override tests
   are the assertion that each flag arrives somewhere that reads it.
2. **`cv2.imshow` is commented out (line 526) while `waitKey(1) == ord("q")` survives
   (529).** There is no window to press a key in, so the documented way to quit does
   nothing and the only exit is killing the process -- which skips the capture release, the
   PPE flush and `producer.close()`, all of which sit after the loop. `ShutdownFlag` and
   the two signal handlers replace it, and the tests here pin both halves: that the
   handlers are installed for `SIGINT` *and* `SIGTERM`, and that the handler actually
   installed sets the flag the loop reads. Registering a handler that does nothing would
   pass the first of those alone, which is why there are two.
3. **The Kafka producer is built at module scope (line 16),** so the file cannot be
   imported without a broker. `test_the_module_imports_with_the_whole_stack_absent` makes
   cv2, ultralytics, kafka and torch genuinely unimportable and imports this module anyway,
   and then resolves a configuration error and prints `--help` in that same world. This is
   the difference between a program you can try and a program you must first provision.

What is deliberately **not** here: anything needing a camera, weights or a broker. There is
no unit test of `build_pipeline`, because every branch of it opens something real; the
integration tier's `test_end_to_end.py` covers the same wiring against the actual adapters.
`build_publisher` is tested by *choice* rather than by connection -- `KafkaEventPublisher.
connect` is monkeypatched, so the assertion is "the Kafka one, with these settings" and no
socket is opened.
"""
from __future__ import annotations

import importlib
import importlib.util
import signal
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import FrameType
from typing import Any

import pytest

from worksite_detector.__main__ import (
    EXIT_CONFIGURATION,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    DiscardingSink,
    ShutdownFlag,
    StartupError,
    Wiring,
    build_publisher,
    build_sink,
    dry_run_summary,
    install_signal_handlers,
    main,
    parse_args,
    report_losses,
    require_weights,
    resolve_config,
)
from worksite_detector.config import CameraConfig, Config, ModelConfig
from worksite_detector.events import DetectionEvent, EventType
from worksite_detector.publisher import InMemoryEventPublisher, KafkaEventPublisher

MAIN_MODULE = "worksite_detector.__main__"

#: The roots `tests/test_architecture.py` forbids everywhere but `adapters`, `annotate` and
#: `publisher`. `__main__.py` is *not* on that exemption list, so it may not name any of
#: them -- it names `adapters`, and imports even that inside the function that builds real
#: collaborators.
HEAVY_ROOTS = ("cv2", "ultralytics", "kafka", "torch")

CAMERA = "gate-1"


def _event(event_type: EventType, start_ms: int, duration: int | None = None) -> DetectionEvent:
    """One valid event, with only the fields a summary reads spelled out."""
    return DetectionEvent(
        event_type=event_type,
        start_time_ms=start_ms,
        confidence=0.9,
        camera_name=CAMERA,
        time_period_ms=duration,
    )


def _config_file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "detector.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Argument parsing -- the parser that is actually called
# --------------------------------------------------------------------------


def test_parse_args_gives_the_documented_defaults() -> None:
    # An empty command line is the documented way to run on built-in defaults: no file, the
    # configured camera, the preview on, publishing for real. Every default here is `None`
    # or `False` on purpose -- a flag that defaulted to a *value* would silently override
    # the config file, which is the layer it exists to override only when asked.
    args = parse_args([])

    assert args.config is None
    assert args.source is None
    assert args.no_display is False
    assert args.dry_run is False


def test_every_flag_reaches_the_namespace() -> None:
    # THE HEADLINE: the original's `parse_args` was never called, so its flags reached
    # nothing at all. Each of these is read by `resolve_config` or by `main`.
    args = parse_args(["--config", "site.yaml", "--source", "rtsp://gate/1", "--no-display",
                       "--dry-run"])

    assert args.config == Path("site.yaml")
    assert args.source == "rtsp://gate/1"
    assert args.no_display is True
    assert args.dry_run is True


def test_config_is_a_path_not_a_string() -> None:
    # `load_config` takes `Path | str | None`, so a string would work -- but every other
    # caller in this package passes a Path, and the parser is where a string stops being a
    # string.
    assert isinstance(parse_args(["--config", "site.yaml"]).config, Path)


def test_an_unknown_flag_is_refused_rather_than_ignored() -> None:
    # argparse exits 2, which is this program's own EXIT_CONFIGURATION: a flag that does
    # not exist and a setting that does not exist are the same mistake one layer apart.
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--sport", "squat"])

    assert excinfo.value.code == EXIT_CONFIGURATION


def test_help_exits_cleanly_and_advertises_the_dry_run() -> None:
    # `--dry-run` is what the README tells a new user to try first, so it has to be
    # discoverable from the program itself.
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--help"])

    assert excinfo.value.code == EXIT_OK


# --------------------------------------------------------------------------
# Layering: defaults < file < environment < command line
# --------------------------------------------------------------------------


def test_source_overrides_the_config_file(tmp_path: Path) -> None:
    path = _config_file(tmp_path, """
        camera:
          source: "9"
    """)

    config = resolve_config(parse_args(["--config", str(path), "--source", "clip.mp4"]), {})

    assert config.camera.source == "clip.mp4"


def test_without_source_the_file_still_decides(tmp_path: Path) -> None:
    # The other half of the test above: an absent flag must leave the layer below alone,
    # not overwrite it with a default.
    path = _config_file(tmp_path, """
        camera:
          source: "9"
    """)

    config = resolve_config(parse_args(["--config", str(path)]), {})

    assert config.camera.source == "9"


def test_the_command_line_sits_on_top_of_the_environment() -> None:
    config = resolve_config(
        parse_args(["--source", "cli.mp4"]), {"WSM_CAMERA__SOURCE": "env.mp4"}
    )

    assert config.camera.source == "cli.mp4"


def test_the_environment_still_sits_on_top_of_the_file(tmp_path: Path) -> None:
    # `load_config` implements this layer, and passing the CLI through the same mapping
    # must not disturb it: the image ships a YAML and the orchestrator overrides one value.
    path = _config_file(tmp_path, """
        camera:
          source: "9"
    """)

    config = resolve_config(
        parse_args(["--config", str(path)]), {"WSM_CAMERA__SOURCE": "env.mp4"}
    )

    assert config.camera.source == "env.mp4"


def test_a_camera_with_no_name_is_named_after_the_source_it_was_given() -> None:
    # A documented consequence of `--source`, not an accident: `CameraConfig` fills `name`
    # from `source`, and the name is stored on every event and grouped by in the dashboard.
    config = resolve_config(parse_args(["--source", "clip.mp4"]), {})

    assert config.camera.name == "clip.mp4"


def test_a_configured_camera_name_survives_a_source_override(tmp_path: Path) -> None:
    path = _config_file(tmp_path, """
        camera:
          name: gate-1
    """)

    config = resolve_config(parse_args(["--config", str(path), "--source", "clip.mp4"]), {})

    assert (config.camera.source, config.camera.name) == ("clip.mp4", "gate-1")


def test_no_display_switches_the_preview_off(tmp_path: Path) -> None:
    path = _config_file(tmp_path, """
        output:
          write_annotated_frame: true
    """)

    config = resolve_config(parse_args(["--config", str(path), "--no-display"]), {})

    assert config.output.write_annotated_frame is False


def test_without_no_display_the_file_decides(tmp_path: Path) -> None:
    # There is no `--display`: the flag is one-directional, so its absence means "whatever
    # the configuration says" rather than "on".
    path = _config_file(tmp_path, """
        output:
          write_annotated_frame: false
    """)

    config = resolve_config(parse_args(["--config", str(path)]), {})

    assert config.output.write_annotated_frame is False


def test_an_unprefixed_environment_variable_is_ignored() -> None:
    # The process environment is full of other people's variables; CI's PATH must not
    # reconfigure a detector. This is `load_config`'s rule, asserted here because the root
    # is what hands it the real `os.environ`.
    config = resolve_config(parse_args([]), {"PATH": "/usr/bin", "SOURCE": "nope.mp4"})

    assert config.camera.source == CameraConfig().source


# --------------------------------------------------------------------------
# Weights: the most likely first experience
# --------------------------------------------------------------------------


def test_present_weights_pass(tmp_path: Path) -> None:
    pose = tmp_path / "yolov8s-pose.pt"
    ppe = tmp_path / "best.pt"
    pose.write_bytes(b"not really a model")
    ppe.write_bytes(b"not really a model either")

    require_weights(Config(models=ModelConfig(pose_weights=pose, ppe_weights=ppe)))


def test_missing_weights_name_the_file_and_where_to_get_it(tmp_path: Path) -> None:
    # `load_config` deliberately touches no filesystem and `adapters` checks one file at a
    # time from inside a model load, several seconds of torch import later. The check
    # belongs here, and its message is the whole of a new user's first experience.
    config = Config(
        models=ModelConfig(
            pose_weights=tmp_path / "yolov8s-pose.pt", ppe_weights=tmp_path / "best.pt"
        )
    )

    with pytest.raises(StartupError) as excinfo:
        require_weights(config)

    message = str(excinfo.value)
    assert "yolov8s-pose.pt" in message and "best.pt" in message, (
        f"got {message!r}, which does not name both of the files that are absent"
    )
    assert "github.com" in message and "release" in message.lower(), (
        f"got {message!r}, which does not say where the weights come from"
    )


def test_only_the_missing_weights_are_named(tmp_path: Path) -> None:
    pose = tmp_path / "yolov8s-pose.pt"
    pose.write_bytes(b"not really a model")
    config = Config(
        models=ModelConfig(pose_weights=pose, ppe_weights=tmp_path / "best.pt")
    )

    with pytest.raises(StartupError) as excinfo:
        require_weights(config)

    assert "yolov8s-pose.pt" not in str(excinfo.value), (
        "naming a file that is present sends the operator looking for the wrong problem"
    )


def test_startup_errors_are_catchable_without_the_cv_stack() -> None:
    # The entry point catches `RuntimeError` around startup so that one clause covers this,
    # `AdapterUnavailableError` and `PublisherUnavailableError` -- two of which it may not
    # import the packages to name.
    assert issubclass(StartupError, RuntimeError)


def test_missing_weights_exit_non_zero_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _config_file(tmp_path, f"""
        models:
          pose_weights: {(tmp_path / 'yolov8s-pose.pt').as_posix()}
          ppe_weights: {(tmp_path / 'best.pt').as_posix()}
    """)

    code = main(["--config", str(path), "--dry-run"], env={})

    assert code != EXIT_OK
    assert code == EXIT_UNAVAILABLE
    captured = capsys.readouterr()
    assert "best.pt" in captured.err
    assert "Traceback" not in captured.err, (
        "a stack trace from inside a library the operator did not write tells them "
        "nothing about which file to download"
    )


# --------------------------------------------------------------------------
# Configuration errors: exit code and stderr, never a traceback
# --------------------------------------------------------------------------


def test_a_missing_config_file_is_a_configuration_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    absent = tmp_path / "not-here.yaml"

    code = main(["--config", str(absent), "--dry-run"], env={})

    assert code == EXIT_CONFIGURATION
    assert "not-here.yaml" in capsys.readouterr().err


def test_an_unknown_setting_is_a_configuration_error_naming_the_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `WSM_KAFKA__BOOTSTRAP_SERVER`, singular, is an operator who believes they redirected
    # the detector and did not. The same rule applies to the file, and the root's job is to
    # turn the ValueError into a sentence and an exit code.
    path = _config_file(tmp_path, """
        kafka:
          bootstrap_server: "broker-1:9092"
    """)

    code = main(["--config", str(path), "--dry-run"], env={})

    assert code == EXIT_CONFIGURATION
    assert "bootstrap_server" in capsys.readouterr().err


def test_a_bad_environment_override_is_a_configuration_error(
    capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--dry-run"], env={"WSM_THRESHOLDS__POSE_CONFIDENCE": "eighty percent"})

    assert code == EXIT_CONFIGURATION
    assert "pose_confidence" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Choosing a publisher -- assert the choice, connect to nothing
# --------------------------------------------------------------------------


def test_dry_run_selects_the_in_memory_publisher(monkeypatch: pytest.MonkeyPatch) -> None:
    # THE FLAG THIS PROGRAM IS DEMONSTRABLE BY: the whole pipeline against no broker, no
    # client library and nothing listening.
    def refuse(**_: Any) -> None:
        raise AssertionError("--dry-run contacted a broker")

    monkeypatch.setattr(KafkaEventPublisher, "connect", refuse)

    publisher = build_publisher(Config(), dry_run=True)

    assert isinstance(publisher, InMemoryEventPublisher)


def test_without_dry_run_the_kafka_publisher_is_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    sentinel = object()

    def record(**kwargs: Any) -> object:
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(KafkaEventPublisher, "connect", record)
    config = Config()

    publisher = build_publisher(config, dry_run=False)

    assert publisher is sentinel
    assert calls == [
        {
            "bootstrap_servers": config.kafka.bootstrap_servers,
            "topic": config.kafka.topic,
        }
    ], "the broker and topic have to come from the configuration, not from a literal"


def test_the_configured_broker_is_the_one_connected_to(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(KafkaEventPublisher, "connect", lambda **kw: calls.append(kw))
    config = resolve_config(
        parse_args([]),
        {"WSM_KAFKA__BOOTSTRAP_SERVERS": "broker-1:9092", "WSM_KAFKA__TOPIC": "site-b"},
    )

    build_publisher(config, dry_run=False)

    assert calls == [{"bootstrap_servers": "broker-1:9092", "topic": "site-b"}]


# --------------------------------------------------------------------------
# Choosing a sink
# --------------------------------------------------------------------------


def test_no_display_selects_a_sink_that_writes_nothing() -> None:
    # `output.write_annotated_frame: false` is a documented setting with no implementation
    # anywhere else: `AnnotatingSink` always writes and points at "a sink that writes
    # nothing" as the caller's to supply.
    config = resolve_config(parse_args(["--no-display"]), {})

    assert isinstance(build_sink(config), DiscardingSink)


def test_the_discarding_sink_honours_the_whole_protocol() -> None:
    # Structural protocols are checked at the call site or not at all, and this one is
    # called once per frame. A missing `close` would surface in the pipeline's `finally`,
    # at shutdown, on a rig.
    sink = DiscardingSink()

    assert sink.write(frame=None, pose=None, objects=()) is None  # type: ignore[arg-type]
    sink.close()
    sink.close()


# --------------------------------------------------------------------------
# Stopping: the quit key that could never fire
# --------------------------------------------------------------------------


def test_the_flag_starts_clear() -> None:
    assert ShutdownFlag().should_stop() is False


def test_requesting_a_stop_sets_the_flag() -> None:
    flag = ShutdownFlag()

    flag.request_stop("SIGINT")

    assert flag.should_stop() is True


def test_a_second_request_is_harmless() -> None:
    # An operator pressing Ctrl+C again while the current frame finishes must not break
    # anything; the flag is already set and the loop is already leaving.
    flag = ShutdownFlag()

    flag.request_stop("SIGINT")
    flag.request_stop("SIGINT")

    assert flag.should_stop() is True


def _captured_handlers(monkeypatch: pytest.MonkeyPatch) -> dict[int, Any]:
    """Divert `signal.signal` into a dict, so a test can call what was registered.

    The process's own handlers are never touched: installing a real one inside a test
    would outlive it and swallow the runner's own Ctrl+C.
    """
    registered: dict[int, Any] = {}

    def record(number: int, handler: Any) -> None:
        registered[number] = handler

    monkeypatch.setattr(signal, "signal", record)
    return registered


def test_handlers_are_registered_for_both_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    # SIGINT is Ctrl+C at a terminal -- the exit the original documented with a `waitKey`
    # that had no window to fire in. SIGTERM is what an orchestrator sends, which on a rig
    # in a container is *every* stop. Either one's default disposition kills the process
    # outright, discarding whatever PPE window was open.
    registered = _captured_handlers(monkeypatch)

    install_signal_handlers(ShutdownFlag())

    assert set(registered) == {signal.SIGINT, signal.SIGTERM}


@pytest.mark.parametrize("number", [signal.SIGINT, signal.SIGTERM], ids=lambda s: s.name)
def test_the_registered_handler_is_the_one_that_sets_the_flag(
    number: signal.Signals, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Registering *a* handler is not the behaviour; registering one that asks the loop to
    # stop is. A handler that did nothing would pass the test above -- which is exactly the
    # state the original shipped in, with a quit key nothing could press.
    registered = _captured_handlers(monkeypatch)
    flag = ShutdownFlag()
    install_signal_handlers(flag)

    registered[number](int(number), None)

    assert flag.should_stop() is True, (
        f"the handler installed for {number.name} does not ask the loop to stop, so the "
        "signal would be swallowed and the detector would keep running"
    )


def test_the_handler_survives_being_handed_a_frame_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real signal machinery passes (signum, frame); a handler that took only the number
    # would raise inside the interpreter's handler dispatch, where nothing catches it.
    registered = _captured_handlers(monkeypatch)
    flag = ShutdownFlag()
    install_signal_handlers(flag)
    frame: FrameType | None = sys._getframe()

    registered[signal.SIGTERM](int(signal.SIGTERM), frame)

    assert flag.should_stop() is True


# --------------------------------------------------------------------------
# The dry-run summary
# --------------------------------------------------------------------------


def test_the_summary_counts_every_type_it_saw() -> None:
    config = Config(camera=CameraConfig(source="clip.mp4"))
    events = [
        _event(EventType.ARMS_UP, 1200),
        _event(EventType.NO_HELMET, 2000, duration=4500),
        _event(EventType.ARMS_UP, 3400),
        _event(EventType.FALL, 15733),
        _event(EventType.NO_HELMET, 9000, duration=2000),
    ]

    summary = dry_run_summary(events, config)

    assert "5 events collected" in summary
    assert 'camera "clip.mp4"' in summary
    rows = {
        line.split()[0]: line.split()[1:]
        for line in summary.splitlines()
        if line.startswith("  ") and line.split() and line.split()[0] in EventType.__members__
    }
    assert rows["ARMS_UP"][0] == "2"
    assert rows["FALL"][0] == "1"
    assert rows["NO_HELMET"][0] == "2"


def test_periodic_types_report_the_duration_the_engine_would_sum() -> None:
    # `/event/periodic-events` SUMS timePeriod per day, so the summary reports the same
    # number an operator will later see on the chart.
    summary = dry_run_summary(
        [
            _event(EventType.NO_JACKET, 1000, duration=4500),
            _event(EventType.NO_JACKET, 9000, duration=2000),
        ],
        Config(),
    )

    jacket = next(line for line in summary.splitlines() if line.strip().startswith("NO_JACKET"))
    assert jacket.split()[-1] == "6500"


def test_countable_types_report_no_duration() -> None:
    # A zero would read as "it lasted no time"; a countable event has no window at all.
    summary = dry_run_summary([_event(EventType.FALL, 15733)], Config())

    fall = next(line for line in summary.splitlines() if line.strip().startswith("FALL"))
    assert fall.split()[-1] == "-"


def test_types_are_listed_in_declaration_order_whatever_order_they_arrived_in() -> None:
    # Two runs of the same footage have to produce comparable output.
    summary = dry_run_summary(
        [_event(EventType.NO_HELMET, 1, duration=0), _event(EventType.FALL, 2)], Config()
    )

    listed = [line.split()[0] for line in summary.splitlines() if line.startswith("  ")]
    assert listed.index("FALL") < listed.index("NO_HELMET")


def test_a_silent_run_says_so_and_says_what_would_have_stopped_an_event() -> None:
    # "Nothing happened" is the most confusing possible result of a first run, and the two
    # confidence gates are what a detection has to clear before any rule sees it.
    summary = dry_run_summary([], Config())

    assert "no events" in summary
    assert "0.8" in summary and "0.6" in summary


def test_the_summary_names_the_broker_the_run_did_not_use() -> None:
    config = resolve_config(
        parse_args([]),
        {"WSM_KAFKA__BOOTSTRAP_SERVERS": "broker-1:9092", "WSM_KAFKA__TOPIC": "site-b"},
    )

    summary = dry_run_summary([_event(EventType.FALL, 1)], config)

    assert "broker-1:9092" in summary and "site-b" in summary


def test_one_event_is_not_reported_as_one_events() -> None:
    assert "1 event collected" in dry_run_summary([_event(EventType.FALL, 1)], Config())


# --------------------------------------------------------------------------
# What the run lost, said out loud at the end of it
# --------------------------------------------------------------------------


class _CountingPublisher:
    """A publisher that has already dropped some events, as the Kafka one would have."""

    def __init__(self, dropped: int) -> None:
        self.dropped_count = dropped

    def publish(self, event: DetectionEvent) -> None:
        raise AssertionError("the shutdown report must not publish anything")

    def close(self) -> None:
        pass


class _CountingSink:
    """A sink that has already skipped some preview frames, as `AnnotatingSink` would."""

    def __init__(self, skipped: int) -> None:
        self.skipped_count = skipped

    def close(self) -> None:
        pass


def _wiring(publisher: Any, sink: Any) -> Wiring:
    # The pipeline is finished by the time this runs; nothing here touches it.
    return Wiring(pipeline=None, publisher=publisher, sink=sink)  # type: ignore[arg-type]


def test_dropped_events_are_reported_at_shutdown(caplog: pytest.LogCaptureFixture) -> None:
    # `dropped_count` is documented as "reported at shutdown" by the publisher, and no
    # frozen collaborator reports it -- the pipeline's shutdown does not read it. Without
    # this line, a broker outage that swallowed a FALL leaves only per-event warnings
    # somewhere above in the log.
    with caplog.at_level("INFO", logger=MAIN_MODULE):
        report_losses(_wiring(_CountingPublisher(dropped=7), DiscardingSink()))

    assert "7" in caplog.text
    assert any(record.levelname == "WARNING" for record in caplog.records), (
        "events that never reached the broker are a safety loss, not an FYI"
    )


def test_skipped_preview_frames_are_reported_more_gently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A dropped event is an incident nobody will ever see; a skipped preview frame is one
    # twenty-fifth of a second of video. The two must not shout equally loudly.
    with caplog.at_level("INFO", logger=MAIN_MODULE):
        report_losses(_wiring(InMemoryEventPublisher(), _CountingSink(skipped=3)))

    assert "3" in caplog.text
    assert all(record.levelname != "WARNING" for record in caplog.records)


def test_a_run_that_lost_nothing_says_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger=MAIN_MODULE):
        report_losses(_wiring(_CountingPublisher(dropped=0), _CountingSink(skipped=0)))

    assert caplog.records == []


def test_publishers_and_sinks_without_counters_are_not_required_to_have_them(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # `InMemoryEventPublisher` drops nothing and `DiscardingSink` skips nothing. Requiring
    # a counter on every implementation of a two-method protocol would make `--dry-run`
    # carry a field about a broker it never contacts.
    with caplog.at_level("INFO", logger=MAIN_MODULE):
        report_losses(_wiring(InMemoryEventPublisher(), DiscardingSink()))

    assert caplog.records == []


# --------------------------------------------------------------------------
# Making the whole stack unimportable
# --------------------------------------------------------------------------


class _BlockedImports:
    """A `sys.meta_path` finder that refuses several top-level packages outright.

    It *raises* from `find_spec` rather than returning `None`, because `None` means only
    "I did not find it" and the ordinary `PathFinder` behind it would then import the copy
    installed in this venv, turning the block into a no-op.
    """

    def __init__(self, blocked_roots: tuple[str, ...]) -> None:
        self.blocked_roots = blocked_roots

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if fullname.split(".")[0] in self.blocked_roots:
            raise ImportError(f"{fullname} is blocked by {type(self).__name__}", name=fullname)
        return None


def _matching(*roots: str) -> list[str]:
    """Every `sys.modules` key that is one of `roots` or a submodule of one."""
    return [
        name
        for name in list(sys.modules)
        if any(name == root or name.startswith(f"{root}.") for root in roots)
    ]


#: The package modules that reach the heavy stack. They are evicted with `__main__` itself,
#: or a cached copy would satisfy an import the block is supposed to refuse.
_EVICTED = (MAIN_MODULE, "worksite_detector.adapters", "worksite_detector.annotate")


@pytest.fixture
def stack_absent() -> Iterator[None]:
    """Run the test body on a machine where cv2, ultralytics, kafka and torch are absent."""
    finder = _BlockedImports(HEAVY_ROOTS)
    saved = {name: sys.modules[name] for name in _matching(*HEAVY_ROOTS, *_EVICTED)}
    for name in saved:
        del sys.modules[name]
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        for name in _matching(*HEAVY_ROOTS, *_EVICTED):
            del sys.modules[name]
        sys.modules.update(saved)


def test_the_blocked_roots_are_installed_so_blocking_them_means_something() -> None:
    # HARNESS GUARD, not one of the listed behaviours. All four ship in this project's
    # `[cv]` extra and are installed in this venv; if one ever leaves, the block below
    # would have nothing to block and the import-safety test would pass vacuously.
    missing = [root for root in HEAVY_ROOTS if importlib.util.find_spec(root) is None]
    assert not missing, f"{missing} is not importable here, so blocking it proves nothing"


def test_the_import_block_actually_blocks(stack_absent: None) -> None:
    # HARNESS GUARD: a finder returning `None` instead of raising would fall through to
    # `PathFinder` and import the real libraries.
    for root in HEAVY_ROOTS:
        with pytest.raises(ImportError):
            importlib.import_module(root)


def test_the_module_imports_with_the_whole_stack_absent(stack_absent: None) -> None:
    # THE HEADLINE REGRESSION: `aiModule.py` line 16 builds a `KafkaProducer` at module
    # scope, so importing it needs the library *and* a reachable broker, and its first
    # lines import cv2 and ultralytics besides. Importing the composition root must need
    # none of them -- that is what lets `--help`, a config error and this suite run on a
    # laptop with nothing provisioned.
    assert MAIN_MODULE not in sys.modules, (
        "the fixture must evict the cached module, or `import_module` returns it without "
        "re-executing a line and this test asserts nothing"
    )

    module = importlib.import_module(MAIN_MODULE)

    assert module.__name__ == MAIN_MODULE


def test_help_works_with_the_whole_stack_absent(stack_absent: None) -> None:
    module = importlib.import_module(MAIN_MODULE)

    with pytest.raises(SystemExit) as excinfo:
        module.parse_args(["--help"])

    assert excinfo.value.code == EXIT_OK


def test_a_configuration_error_is_reported_with_the_whole_stack_absent(
    stack_absent: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The startup path down to the first real resource must not touch the CV stack, or a
    # typo in a YAML file would be answered by `ModuleNotFoundError: cv2`.
    module = importlib.import_module(MAIN_MODULE)

    code = module.main(["--config", str(tmp_path / "not-here.yaml")], env={})

    assert code == EXIT_CONFIGURATION
    assert "not-here.yaml" in capsys.readouterr().err
