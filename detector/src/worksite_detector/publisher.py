"""The one seam that talks to Kafka, and the only place allowed to import it.

``aiModule.py`` line 16 is, at module scope::

    producer = KafkaProducer(bootstrap_servers='localhost:9092')

so importing that file opens a broker connection. Not calling anything in it --
*importing* it. On a machine with no reachable broker the module cannot be loaded
at all: not by a test, not by ``--help``, not by a linter, not by an editor
resolving a symbol.

That is not a theoretical cost, and the measurement is the reason for the shape of
this module. A stub faithful to that one line, with this package's test suite
pointed at it, collects **zero tests**: ``NoBrokersAvailable`` fires during
collection, before a single test function is reached, so the suite reports neither
a pass nor a failure -- there is nothing to report on. One line at module scope is
why none of the original 547 were ever testable. It is also the strongest argument
against ever moving the import below back out of ``connect``: the cost is not one
awkward module, it is the whole suite, silently.

The split that makes every behaviour here reachable from a unit test:

* **``__init__`` takes an already-built producer.** The client is injected and
  nothing in this class constructs a connection, so the send/flush/close protocol
  can be driven end to end by a fake that records what it was asked to do.
* **``connect`` is the only function that imports ``kafka``,** and it imports it
  inside the function body. ``tests/test_architecture.py`` proves that
  structurally, by reading the AST; ``tests/test_publisher.py`` proves the
  consequence behaviourally, by making ``kafka`` genuinely unimportable and then
  importing this module anyway. Both are needed: an AST check cannot see a lazy
  import that still explodes, and a runtime check cannot see an import that
  happens to be satisfied.

**``dropped_count`` and the warning per drop are one mechanism, not two.** None of
the original's five publish blocks is wrapped in ``try``, so a broker hiccup raises
out of the frame loop and stops detection: the camera stops, and the events that
would have been buffered are not merely lost, they are never even observed. Losing
events is the acceptable failure at a worksite; losing the detector is not. But an
exception swallowed quietly replaces a loud failure with a silent one, which is the
trade this codebase makes everywhere else and precisely the one being undone here.
So a failed publish costs exactly one WARNING on this module's own logger -- named
``worksite_detector.publisher``, so an operator can raise or silence this seam
alone -- naming the event type and the underlying error, while ``dropped_count``
carries the aggregate for the pipeline to report at shutdown.

One record per dropped event is deliberate, spam included. A broker down for an
hour produces an enormous number of records, and that is the correct trade:
silently losing a FALL -- the event that mails every user in the engine's database
-- is a worse outcome than a noisy log; ``dropped_count`` already serves anyone who
wants the number rather than the detail; and an operator whose broker is down has
to learn it from the logs rather than from an empty dashboard three days later.
Throttling, aggregating or logging only the first failure turns this straight back
into the silent loss it exists to prevent.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from worksite_detector.events import DetectionEvent

# `worksite_detector.publisher`, which is the name an operator configures to raise
# or silence this seam independently of the rest of the detector.
_LOGGER = logging.getLogger(__name__)


@runtime_checkable
class EventPublisher(Protocol):
    """Where a detected event goes.

    The pipeline is typed against this and never against either concrete class,
    which is what lets ``--dry-run`` swap ``InMemoryEventPublisher`` in at runtime
    on a machine with no broker and no client library.

    ``@runtime_checkable`` so that swap can be asserted with ``isinstance``, which
    checks method *names* only: it catches a rename or a missing method -- the
    drift a duck-typed swap would otherwise discover on a live rig -- and not a
    changed signature, which is mypy's job at the call site.
    """

    def publish(self, event: DetectionEvent) -> None:
        """Publish one event.

        Implementations must not raise on a transport failure; the frame loop
        calling this has no useful response to one and must keep reading frames.
        """

    def close(self) -> None:
        """Release whatever the implementation holds.

        Called from the pipeline's ``finally``, so it runs on the failure path
        too, and it may run twice.
        """


class PublisherUnavailableError(RuntimeError):
    """A publisher could not be constructed at all.

    A ``RuntimeError`` and deliberately not an ``ImportError``: the entry point
    wraps startup in ``except RuntimeError``, and the caller has to be able to name
    and catch this without importing ``kafka`` -- subclassing ``ImportError`` would
    make it the very failure it exists to replace.

    Raised only by ``KafkaEventPublisher.connect``. Once a producer exists, a
    failure to send is counted and logged, never raised.
    """


class InMemoryEventPublisher:
    """Collects events in memory instead of sending them anywhere.

    Production code, not a test double: ``--dry-run`` uses it to run the whole
    detector against a machine with no broker and print what would have been
    published. It is specified as tightly as the Kafka implementation because it
    runs the same pipeline, and it is what an operator sees when they are checking
    a new camera's tuning before pointing it at a broker.
    """

    def __init__(self) -> None:
        """Start empty and open."""
        # Per instance, never class level: a list on the class would be shared by
        # every publisher in the process, so one dry run would print another's
        # events and every test of this class would pass for the wrong reason.
        self.events: list[DetectionEvent] = []
        self.closed: bool = False

    def publish(self, event: DetectionEvent) -> None:
        """Append ``event`` to ``events``.

        Order is exactly the order published: nothing is sorted and nothing is
        de-duplicated, because the list is the run's transcript and a transcript
        out of order is worse than none.

        Raises:
            RuntimeError: If this publisher is closed, and the rejected event is
                not recorded. Accepting it silently would hide a shutdown-ordering
                bug in the pipeline -- the event would sit in a list nobody reads
                again, which is exactly how the original lost ``NO_JACKET`` for the
                life of the project: detected, then never reported.
        """
        if self.closed:
            raise RuntimeError(
                f"cannot publish {event.event_type.value}: this publisher is already closed, "
                "so the event was produced after the sink shut down and nothing would ever "
                "read it. Publish before close, or the detection is lost in silence."
            )
        self.events.append(event)

    def close(self) -> None:
        """Mark the publisher closed, keeping everything collected so far.

        There is no connection to release; the flag exists so that a post-close
        publish is refused rather than quietly accepted. The collected events must
        survive, because ``--dry-run`` prints them *after* the pipeline has shut
        its sink down -- clearing here would print an empty run.

        Idempotent, because shutdown paths routinely run twice (a signal handler
        and a ``finally``).
        """
        self.closed = True


class KafkaEventPublisher:
    """Publishes events to one Kafka topic, and survives the broker going away.

    The topic is constructor state rather than the literal ``'rawEvents'`` repeated
    at five call sites, and serialisation is ``DetectionEvent.to_json`` rather than
    a payload dict rebuilt inline at each of them -- which is how the original came
    to send ``timePeriod`` in seconds from some branches and never from others.

    One instance per sink. The dropped counter is mutable and unsynchronised,
    matching the single-threaded frame loop that owns it.
    """

    def __init__(self, producer: Any, topic: str) -> None:
        """Wrap an already-constructed producer.

        ``producer`` is anything honouring the three calls used here:
        ``send(topic, value=..., key=...)``, ``flush()`` and ``close()``. Taking it
        as an argument rather than building it is what makes every behaviour of
        this class reachable without a broker.

        It is annotated ``Any`` on purpose. This module may not name
        ``KafkaProducer`` -- not even under ``typing.TYPE_CHECKING``, which would
        put ``kafka`` back at module scope for every type checker and every reader
        who then copies the pattern -- and the looseness is the seam rather than a
        concession: a structural three-method contract is genuinely all this class
        depends on.

        ``topic`` is not validated here. ``KafkaConfig`` already refuses an empty
        one at load time, and a second, later check would report the same mistake
        from a worse place.
        """
        self._producer = producer
        self._topic = topic
        self.dropped_count: int = 0

    @classmethod
    def connect(cls, bootstrap_servers: str, topic: str) -> KafkaEventPublisher:
        """Build a real Kafka producer for ``bootstrap_servers`` and wrap it.

        The only function in this package that imports ``kafka``, and it imports it
        in its own body -- see the module docstring for the collected-zero-tests
        result that rule comes from.

        No ``value_serializer`` is configured: ``DetectionEvent.to_json`` already
        returns the UTF-8 bytes of the wire format the engine binds, and a
        serialiser here would encode them a second time.

        Raises:
            PublisherUnavailableError: If the client library is missing, or if a
                producer cannot be constructed against ``bootstrap_servers``.
                Both are wrapped, and for the same reason: neither ``ImportError``
                nor the client's own ``NoBrokersAvailable`` can be caught by a
                caller that is not allowed to import ``kafka``. The message names
                the package to install, because a bare "No module named 'kafka'"
                out of the middle of a deploy names the import root and the two
                differ here.
        """
        try:
            from kafka import KafkaProducer
        except ImportError as exc:
            raise PublisherUnavailableError(
                "the Kafka client library is not installed, so no event can be published. "
                "The import root is `kafka` but the package is not: install it with "
                "`pip install kafka-python-ng` (the maintained kafka-python fork this "
                "project pins in its [cv] extra), or run the detector with --dry-run, "
                "which publishes nothing and needs neither the library nor a broker."
            ) from exc

        try:
            producer = KafkaProducer(bootstrap_servers=bootstrap_servers)
        except Exception as exc:
            # The client raises its own exception types for an unreachable or
            # misconfigured broker, and this is startup: refusing to start with an
            # actionable, catchable error is right here, whereas the same failure
            # mid-run is a dropped event and nothing more.
            raise PublisherUnavailableError(
                f"could not connect a Kafka producer to {bootstrap_servers!r}: "
                f"{type(exc).__name__}: {exc}. Check the broker address and that the "
                "broker is reachable from this host, or run the detector with --dry-run."
            ) from exc

        return cls(producer=producer, topic=topic)

    def publish(self, event: DetectionEvent) -> None:
        """Send one event to the configured topic, then flush.

        Flushing after every send preserves the original's behaviour and is a
        durability choice rather than an oversight: the event is on the broker
        before the next frame is read, so a hard kill loses nothing already
        detected. Batching it away would be a change to that guarantee, not an
        optimisation. The send result is deliberately not waited on -- blocking on
        the future would stall the frame loop on a slow broker, and the flush is
        what provides the durability.

        The partition key is the event's own start time, so publishing the same
        event twice produces the same key. The original used
        ``str(time.time()).encode('utf-8')``, a fresh value on every call, so two
        identical events landed on different partitions and no key was ever
        reproducible. Nothing reads the key back; being deterministic is the entire
        requirement, and the event's own timestamp is the cheapest thing that is.

        Never raises. A failure -- an unreachable broker, or an event that cannot be
        serialised -- increments ``dropped_count`` and costs one WARNING, and the
        caller carries on reading frames.
        """
        try:
            self._producer.send(
                self._topic,
                value=event.to_json(),
                key=str(event.start_time_ms).encode("utf-8"),
            )
            self._producer.flush()
        except Exception as exc:
            # `Exception` and not the client's `KafkaError`, which this module may
            # not name; and not `BaseException`, so a Ctrl+C during a send still
            # stops the detector instead of being counted as a dropped event.
            self.dropped_count += 1
            # The exception's class *and* its message: `str(exc)` alone loses the
            # type, and the type is what separates a broker outage from a
            # serialisation bug for someone reading the log without a debugger.
            # Interpolated rather than attached with exc_info, because at one record
            # per drop a traceback per record turns a noisy log into an unreadable
            # one, and the frames would be inside the client library anyway.
            _LOGGER.warning(
                "dropped %s event from camera %r: publishing to topic %r failed with %s: %s",
                event.event_type.value,
                event.camera_name,
                self._topic,
                type(exc).__name__,
                exc,
            )

    def close(self) -> None:
        """Close the underlying producer.

        The pipeline calls this from a ``finally`` so it reaches the real client on
        the failure path too: the original closed its producer only on the normal
        path, and anything raising out of the frame loop leaked the connection and
        abandoned whatever the client still held buffered.
        """
        self._producer.close()
