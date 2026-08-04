"""Unit tests for `worksite_detector.publisher` -- the one seam that touches Kafka.

`aiModule.py` line 16 is, at module scope:

    producer = KafkaProducer(bootstrap_servers='localhost:9092')

so importing that file opens a broker connection. Not calling anything in it --
*importing* it. On a machine without a reachable Kafka the module cannot be loaded
at all: not by a test, not by `--help`, not by a linter, not by an editor's
autocomplete. That single line is the reason none of the original 547 lines were
ever testable, and it is the defect this module exists to end.

The replacement splits the problem in two, and the split is what makes every
behaviour below reachable from a unit test:

* **`__init__` takes an already-built producer.** The Kafka client is injected, so
  the send/flush/close protocol can be driven by a fake that records what it was
  asked to do.
* **`connect` is the only place that imports `kafka`,** and it imports it *inside*
  the function. `tests/test_architecture.py::test_publisher_defers_kafka_import`
  proves that structurally, by reading the AST; this file proves the consequence
  behaviourally, by making `kafka` genuinely unimportable and then importing the
  module anyway. Both are needed: the AST check cannot see a lazy import that still
  explodes, and the runtime check cannot see an import that happens to be satisfied.

The other defects pinned here, all of them in the four near-identical publish blocks
at `aiModule.py` 350-352, 389-392, 449-451, 480-482 and 505-509:

1. **`key = str(time.time()).encode('utf-8')`** -- a fresh value on every call, so two
   identical events land on different partitions and no key is ever reproducible.
   The key is partitioning only; it just has to be *deterministic*.
2. **The topic `'rawEvents'` is a literal repeated at all five call sites.** One site
   with a different broker layout means five edits, or four.
3. **The payload dict is rebuilt inline at each site**, so the wire format could (and
   did) drift between branches. There is one serialisation path now: `event.to_json()`.
4. **Nothing is wrapped in `try`.** A broker hiccup raises out of the frame loop and
   kills detection: the camera stops, and the events that would have been buffered are
   not merely lost, they are never even observed. Losing events is the acceptable
   failure here; stopping the detector is not -- but the loss has to be *visible*, or
   the fix for a loud failure is a silent one. Each dropped event costs one WARNING on
   the `worksite_detector.publisher` logger, naming the event type and the underlying
   error, and `dropped_count` carries the aggregate. The reasoning behind logging every
   single one, spam and all, is written out at
   `test_each_dropped_event_logs_one_warning`.

`InMemoryEventPublisher` is production code, not a test double -- `--dry-run` uses it
to print what would have been sent -- which is why it is specified as tightly as the
Kafka one and why `close` must not discard what it collected.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from collections.abc import Iterator
from typing import Any, NamedTuple

import pytest
from worksite_detector.events import DetectionEvent, EventType
from worksite_detector.publisher import (
    EventPublisher,
    InMemoryEventPublisher,
    KafkaEventPublisher,
    PublisherUnavailableError,
)

#: Also the logger name. `logging.getLogger(__name__)` inside the module yields exactly
#: this, which is what lets an operator raise or silence this one seam in isolation.
PUBLISHER_MODULE = "worksite_detector.publisher"

#: Deliberately NOT `'rawEvents'`. The topic is constructor state; an implementation
#: that carries `aiModule.py`'s literal through fails every test that uses this.
TOPIC = "site-b-rawEvents"

#: A fixed instant, so the key below can be written out in full rather than recomputed
#: by the same expression the implementation uses.
START_MS = 1_700_000_000_000

#: `str(START_MS).encode()`, spelled literally.
EXPECTED_KEY = b"1700000000000"

CAMERA = "kamera-üst"

CONF = 0.87


def _event(**overrides: Any) -> DetectionEvent:
    """A valid countable event, with fields replaced so each test shows only what it varies."""
    fields: dict[str, Any] = {
        "event_type": EventType.FALL,
        "start_time_ms": START_MS,
        "confidence": CONF,
        "camera_name": CAMERA,
    }
    return DetectionEvent(**{**fields, **overrides})


# --------------------------------------------------------------------------
# Fakes
#
# Hand-written rather than `unittest.mock`, matching `tests/_support/fakes.py`: a
# `Mock` answers any attribute with another `Mock`, so a publisher that called the
# wrong method, or the right one with the wrong arguments, would still look green.
# These record instead, and the recording is the assertion surface.
# --------------------------------------------------------------------------


class BrokerDown(Exception):
    """What the real client raises when it cannot reach the broker.

    A plain `Exception` subclass on purpose: `publisher.py` may not import `kafka` at
    module level, so it cannot name `KafkaError` in an `except` clause and must catch
    the general case.
    """


class SentRecord(NamedTuple):
    """One `producer.send(...)` call, as the fake saw it."""

    topic: str
    value: Any
    key: Any


class _SendFuture:
    """What a real `KafkaProducer.send` hands back.

    Returning `None` instead would make an implementation that blocks on the future
    fail with a swallowed `AttributeError` -- invisible, because the swallowing is
    itself required behaviour. This records the call in the same order log so the
    failure shows up as an extra entry rather than as a mystery.
    """

    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def get(self, timeout: float | None = None) -> None:
        self._calls.append("future.get")


class FakeProducer:
    """Records the send/flush/close protocol a `KafkaProducer` would have received.

    Signatures mirror `kafka-python`'s, so an implementation may pass `value` and
    `key` positionally or by keyword and this fake sees the same thing either way.
    """

    def __init__(self, *, fails_with: Exception | None = None) -> None:
        self.sends: list[SentRecord] = []
        self.calls: list[str] = []
        self.flush_count = 0
        self.close_count = 0
        self._fails_with = fails_with

    def send(self, topic: str, value: Any = None, key: Any = None) -> _SendFuture:
        self.calls.append("send")
        self.sends.append(SentRecord(topic=topic, value=value, key=key))
        if self._fails_with is not None:
            raise self._fails_with
        return _SendFuture(self.calls)

    def flush(self, timeout: float | None = None) -> None:
        self.calls.append("flush")
        self.flush_count += 1

    def close(self, timeout: float | None = None) -> None:
        self.calls.append("close")
        self.close_count += 1


def _kafka_publisher(**kwargs: Any) -> tuple[KafkaEventPublisher, FakeProducer]:
    """A publisher wired to a fresh fake, and the fake to assert against."""
    producer = FakeProducer(**kwargs)
    return KafkaEventPublisher(producer=producer, topic=TOPIC), producer


def _rendered(record: logging.LogRecord) -> str:
    """What an operator actually reads, for one record.

    The formatted message, plus the traceback when the call passed `exc_info`. Both
    spellings -- interpolating the exception into the message, or attaching it -- put
    the cause in front of whoever is reading the log, which is the property under test.
    Which of the two an implementation picks is its own business.
    """
    text = record.getMessage()
    if record.exc_info is not None:
        text = f"{text}\n{logging.Formatter().formatException(record.exc_info)}"
    return text


def _drop_three(caplog: pytest.LogCaptureFixture) -> tuple[KafkaEventPublisher, BrokerDown,
                                                           tuple[EventType, ...]]:
    """Publish three events of distinct types into a producer that always raises.

    Distinct types, because a log line that repeats the first event's details -- or that
    names no event at all -- is indistinguishable from a correct one when every event in
    the test is the same.
    """
    failure = BrokerDown("no brokers available")
    publisher, _producer = _kafka_publisher(fails_with=failure)
    types = (EventType.FALL, EventType.ARMS_UP, EventType.FRONT_BEND)

    with caplog.at_level(logging.WARNING, logger=PUBLISHER_MODULE):
        for offset, event_type in enumerate(types):
            publisher.publish(_event(event_type=event_type, start_time_ms=START_MS + offset))

    return publisher, failure, types


# --------------------------------------------------------------------------
# Making `kafka` genuinely unimportable
# --------------------------------------------------------------------------


class _BlockedImport:
    """A `sys.meta_path` finder that refuses one top-level package outright.

    It *raises* from `find_spec` rather than returning `None`, because `None` means
    only "I did not find it" and the next finder on the path -- the ordinary
    `PathFinder`, which can find the `kafka-python-ng` installed in this venv --
    would then import it and the block would be a no-op.
    """

    def __init__(self, blocked_root: str) -> None:
        self.blocked_root = blocked_root

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if fullname.split(".")[0] == self.blocked_root:
            raise ImportError(
                f"{fullname} is blocked by {type(self).__name__} for this test",
                name=fullname,
            )
        return None


def _matching(*roots: str) -> list[str]:
    """Every `sys.modules` key that is one of `roots` or a submodule of one."""
    return [
        name
        for name in list(sys.modules)
        if any(name == root or name.startswith(f"{root}.") for root in roots)
    ]


@pytest.fixture
def kafka_absent() -> Iterator[None]:
    """Run the test body on a machine where `import kafka` fails.

    Three pieces of global state are touched and all three are restored in `finally`,
    so a failing test cannot leave the rest of the session running against a broken
    import system: the meta path, the cached `kafka` modules, and the cached
    `worksite_detector.publisher` (which must be evicted, or `import_module` would
    return the already-loaded copy without re-executing it and the test would pass
    without having imported anything).
    """
    finder = _BlockedImport("kafka")
    saved = {name: sys.modules[name] for name in _matching("kafka", PUBLISHER_MODULE)}
    for name in saved:
        del sys.modules[name]
    sys.meta_path.insert(0, finder)
    try:
        try:
            importlib.import_module("kafka")
        except ImportError:
            pass
        else:
            raise AssertionError(
                "`import kafka` still succeeded with the block installed, so every test "
                "using this fixture would pass vacuously -- kafka-python-ng IS installed "
                "in this venv, so absence proves nothing here"
            )
        yield
    finally:
        sys.meta_path.remove(finder)
        for name in _matching("kafka", PUBLISHER_MODULE):
            del sys.modules[name]
        sys.modules.update(saved)


def test_kafka_is_installed_so_blocking_it_means_something() -> None:
    # HARNESS GUARD, not one of the listed behaviours. `kafka-python-ng` ships in this
    # project's `[cv]` extra and is installed in the venv. If it ever leaves, the two
    # import-safety tests below would keep passing while proving nothing, because the
    # block would have nothing left to block.
    assert importlib.util.find_spec("kafka") is not None, (
        "kafka is not importable in this environment, so the meta_path block in the "
        "`kafka_absent` fixture is a no-op and the import-safety tests are vacuous"
    )


def test_import_block_actually_blocks(kafka_absent: None) -> None:
    # HARNESS GUARD, not one of the listed behaviours: proves the fixture's mechanism
    # rather than the module's behaviour. A finder that returned `None` instead of
    # raising would fall through to `PathFinder`, import the real library, and turn
    # `test_module_imports_with_kafka_absent` into a test of nothing at all.
    with pytest.raises(ImportError):
        importlib.import_module("kafka")


# --------------------------------------------------------------------------
# Import safety -- the headline defect
# --------------------------------------------------------------------------


def test_module_imports_with_kafka_absent(kafka_absent: None) -> None:
    # THE HEADLINE REGRESSION: `aiModule.py` line 16 builds a `KafkaProducer` at module
    # scope, so `import aiModule` needs the library AND a broker. Importing the
    # publisher must need neither -- that is what lets `--dry-run`, `--help`, mypy and
    # this entire suite run on a laptop with no Kafka anywhere.
    assert PUBLISHER_MODULE not in sys.modules, (
        "the fixture must evict the cached module, or `import_module` below returns it "
        "without re-executing a single line and this test asserts nothing"
    )

    module = importlib.import_module(PUBLISHER_MODULE)

    assert module.__name__ == PUBLISHER_MODULE


def test_connect_without_kafka_raises_actionable_error(kafka_absent: None) -> None:
    # A bare `ImportError: No module named 'kafka'` out of the middle of a deploy names
    # the import root, not the thing to install -- and the two differ here, because the
    # package that provides `kafka` is `kafka-python`. The error has to say what to type.
    # Names are looked up on the freshly imported module: the classes bound at the top of
    # this file belong to the *other* copy and `pytest.raises` compares by identity.
    module = importlib.import_module(PUBLISHER_MODULE)

    with pytest.raises(module.PublisherUnavailableError) as excinfo:
        module.KafkaEventPublisher.connect(bootstrap_servers="localhost:9092", topic=TOPIC)

    assert "kafka-python" in str(excinfo.value), (
        f"got {str(excinfo.value)!r}, which does not name the pip package to install"
    )
    # And it must be catchable without importing kafka: the entry point wraps startup in
    # `except RuntimeError`. Subclassing `ImportError` would make it the very failure it
    # exists to replace. Asserted on the statically imported class, which is the same
    # declaration -- only a different copy of it.
    assert issubclass(PublisherUnavailableError, RuntimeError) is True


# --------------------------------------------------------------------------
# InMemoryEventPublisher
# --------------------------------------------------------------------------


def test_in_memory_starts_empty_and_open() -> None:
    # A publisher that started `closed=True`, or with a class-level list shared between
    # instances, would make every other test in this section pass for the wrong reason.
    publisher = InMemoryEventPublisher()

    assert (publisher.events, publisher.closed) == ([], False)


def test_in_memory_records_in_order() -> None:
    # `--dry-run` prints this list as the run's transcript, and a transcript out of order
    # is worse than none. Published deliberately out of timestamp order so an
    # implementation that sorts, or that uses a set to de-duplicate, cannot pass.
    publisher = InMemoryEventPublisher()
    third = _event(event_type=EventType.NO_HELMET, start_time_ms=START_MS + 2000,
                   time_period_ms=4500)
    first = _event(start_time_ms=START_MS)
    second = _event(event_type=EventType.ARMS_UP, start_time_ms=START_MS + 1000)

    for event in (third, first, second):
        publisher.publish(event)

    assert publisher.events == [third, first, second]


def test_in_memory_close_sets_flag_and_keeps_events() -> None:
    # `close` mirrors `KafkaEventPublisher.close`, which drops a connection -- but here
    # there is nothing to release, and `--dry-run` prints the collected events AFTER the
    # pipeline has shut its sink down. Clearing on close would print an empty run.
    publisher = InMemoryEventPublisher()
    first = _event()
    second = _event(event_type=EventType.FRONT_BEND, start_time_ms=START_MS + 500)
    publisher.publish(first)
    publisher.publish(second)

    publisher.close()

    assert (publisher.closed, publisher.events) == (True, [first, second])


def test_in_memory_publish_after_close_raises() -> None:
    # Silently accepting a post-close publish would hide a shutdown-ordering bug in the
    # pipeline -- the events would sit in a list nobody reads again, which is exactly how
    # the legacy lost NO_JACKET for the project's whole life: detected, then never
    # reported. The rejected event must also not be recorded, so a `list.append` placed
    # above the guard fails here rather than showing up as a phantom entry downstream.
    publisher = InMemoryEventPublisher()
    kept = _event()
    publisher.publish(kept)
    publisher.close()

    with pytest.raises(RuntimeError):
        publisher.publish(_event(start_time_ms=START_MS + 1))

    assert publisher.events == [kept]


# --------------------------------------------------------------------------
# KafkaEventPublisher -- the send protocol
# --------------------------------------------------------------------------


def test_kafka_sends_to_configured_topic() -> None:
    # `aiModule.py` repeats the literal `'rawEvents'` at all five publish sites. The topic
    # is constructor state now, so a second site or a renamed topic is one argument, not a
    # five-way edit with one branch left behind.
    publisher, producer = _kafka_publisher()

    publisher.publish(_event())

    assert [record.topic for record in producer.sends] == [TOPIC]


def test_kafka_value_is_event_to_json() -> None:
    # One serialisation path, so the wire format cannot fork. The legacy rebuilt the
    # payload dict inline at each of five sites, which is how `timePeriod` came to be sent
    # in seconds from some branches and never from others. Byte-for-byte: a publisher that
    # re-encodes, re-orders keys or hands `send` a `str` fails here rather than on site.
    event = _event(event_type=EventType.NO_HELMET, time_period_ms=4500)
    publisher, producer = _kafka_publisher()

    publisher.publish(event)

    assert [record.value for record in producer.sends] == [event.to_json()]


def test_kafka_key_is_deterministic_bytes() -> None:
    # `key = str(time.time()).encode('utf-8')` (aiModule.py 350, 389, 449, 480, 505) is a
    # fresh value per call, so two identical events partition differently and no key is
    # ever reproducible. The key is only a partitioning hint, so its exact value matters
    # less than its determinism -- published twice here precisely to pin that.
    event = _event()
    publisher, producer = _kafka_publisher()

    publisher.publish(event)
    publisher.publish(event)

    assert [record.key for record in producer.sends] == [EXPECTED_KEY, EXPECTED_KEY]


def test_kafka_flushes_after_each_send() -> None:
    # The legacy flushed after every send (352, 392, 451, 482, 509) and this preserves
    # that: it trades throughput for the property that an event is on the broker before
    # the next frame is read, so a hard kill loses nothing already detected. Batching it
    # away would be a durability change, not an optimisation.
    publisher, producer = _kafka_publisher()

    publisher.publish(_event())

    assert producer.calls == ["send", "flush"], (
        f"got {producer.calls}. A `future.get` entry means the publisher blocks on the "
        f"send result, which stalls the frame loop on a slow broker -- `flush` is what "
        f"provides the durability here."
    )


def test_close_closes_the_producer() -> None:
    # `aiModule.py` line 540 closes the producer only on the normal path; anything raising
    # out of the frame loop leaks the connection and abandons whatever the client still
    # holds in its buffer. The pipeline calls this from a `finally`, so it must reach the
    # real client.
    publisher, producer = _kafka_publisher()

    publisher.close()

    assert producer.close_count == 1


# --------------------------------------------------------------------------
# KafkaEventPublisher -- failure handling
#
# The rule: a broker outage costs events, never the detector. The camera keeps
# running, the frames keep being read, and what could not be sent is counted.
# --------------------------------------------------------------------------


def test_send_failure_is_logged_not_raised() -> None:
    # Nothing in the legacy's five publish blocks is wrapped in `try`, so one unreachable
    # broker raises out of the frame loop and stops detection entirely. A site with no
    # dashboard is bad; a site with no monitoring is the actual hazard. The "logged" half
    # of this contract is pinned by the two tests below.
    publisher, producer = _kafka_publisher(fails_with=BrokerDown("no brokers available"))

    publisher.publish(_event())

    assert publisher.dropped_count == 1


def test_each_dropped_event_logs_one_warning(caplog: pytest.LogCaptureFixture) -> None:
    # Swallowing the exception is required; swallowing it *quietly* would replace a loud
    # failure with a silent one, which is the same trade the legacy made everywhere else
    # in this codebase. One record per dropped event, at WARNING, on the module's own
    # logger so it can be raised or silenced independently of the rest of the detector.
    #
    # DELIBERATE -- DO NOT "IMPROVE" THIS INTO A ONCE-PER-MINUTE SUMMARY. A broker down
    # for an hour produces an enormous number of records, and that is the correct trade
    # here: silently losing a FALL -- the event that mails every user in the database --
    # is a worse outcome than a noisy log. `dropped_count` already carries the aggregate
    # for anyone who wants the number rather than the detail, and an operator whose broker
    # is down has to learn it from the logs rather than from an empty dashboard three days
    # later. Throttling, aggregating or logging only the first failure turns this straight
    # back into the silent loss it exists to prevent.
    _publisher, _failure, types = _drop_three(caplog)

    assert [(record.name, record.levelno) for record in caplog.records] == [
        (PUBLISHER_MODULE, logging.WARNING)
    ] * len(types)


def test_dropped_event_warning_names_the_event_type_and_the_cause(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # "publish failed", three times, tells an operator nothing they can act on. The record
    # has to separate a broker outage from a serialisation bug without anyone attaching a
    # debugger, and it has to say WHICH event was lost -- a dropped FALL is a different
    # incident from a dropped ARMS_UP. Asserted against the rendered record, message and
    # traceback together, because that is the text an operator actually sees.
    _publisher, failure, types = _drop_three(caplog)
    rendered = [_rendered(record) for record in caplog.records]

    assert len(rendered) == len(types), (
        f"expected one record per dropped event, got {len(rendered)}; "
        f"see test_each_dropped_event_logs_one_warning"
    )
    assert [
        (event_type.value in text, str(failure) in text)
        for event_type, text in zip(types, rendered, strict=True)
    ] == [(True, True)] * len(types), f"records read: {rendered}"


def test_dropped_count_starts_at_zero_and_counts_each_failure() -> None:
    # Swallowing an exception without counting it is the other half of the defect: the run
    # looks healthy, the dashboard is simply empty, and nothing anywhere says why. The
    # count is what the pipeline reports at shutdown.
    publisher, _producer = _kafka_publisher(fails_with=BrokerDown("no brokers available"))
    before = publisher.dropped_count

    for offset in range(3):
        publisher.publish(_event(start_time_ms=START_MS + offset))

    assert (before, publisher.dropped_count) == (0, 3)


def test_successful_publish_does_not_increment_dropped_count() -> None:
    # The mirror: a counter incremented on every send, or in a `finally`, reports a
    # healthy run as a total outage and sends someone to look at a broker that is fine.
    publisher, _producer = _kafka_publisher()

    publisher.publish(_event())
    publisher.publish(_event(start_time_ms=START_MS + 1))

    assert publisher.dropped_count == 0


# --------------------------------------------------------------------------
# Protocol
# --------------------------------------------------------------------------


def test_both_implementations_satisfy_the_protocol() -> None:
    # The pipeline is typed against `EventPublisher` and never against either concrete
    # class, which is what lets `--dry-run` swap the in-memory one in at runtime. A
    # renamed or missing method on either side has to fail here, not at the call site on a
    # live rig -- `@runtime_checkable` checks the method names, so this catches exactly
    # the drift that a duck-typed swap would otherwise discover in production.
    in_memory = InMemoryEventPublisher()
    kafka, _producer = _kafka_publisher()

    assert (isinstance(in_memory, EventPublisher), isinstance(kafka, EventPublisher)) == (
        True,
        True,
    )
