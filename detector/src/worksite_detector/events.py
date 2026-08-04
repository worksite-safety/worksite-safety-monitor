"""Safety events and the JSON payload that carries them to the engine.

This module is the producer half of a contract whose consumer is in another
language and another build: events are published to the Kafka topic ``rawEvents``
and bound by Jackson to ``RawEvent.java`` in the engine. That class is annotated
``@JsonIgnoreProperties(ignoreUnknown = true)``, so a payload with a misspelled,
extra or missing key is accepted in silence -- the value simply arrives as null,
becomes an empty column in MongoDB and a gap in the dashboard, with no exception
and no log line on either side. Nothing downstream validates anything. The shape
built here is therefore the only enforcement point in the whole pipeline, which
is why ``tests/test_events.py`` asserts it against the Java source itself rather
than against a copy of the key list.

The parts of the wire format that are decisions rather than consequences:

* **All six keys, always.** Countable events send ``timePeriod`` as null instead
  of omitting it. ``RawEventService.listener`` dereferences ``getTimePeriod()``
  only inside its ``NO_HELMET || NO_JACKET`` branch, so the null is never read,
  and a constant key set keeps the stored documents uniform.
* **``isProcessed`` is the string ``"false"``, not a JSON boolean.** The Java
  field is declared ``String isProcessed`` and every document already in MongoDB
  holds the string, because that is what the original producer sent. A boolean
  would either be coerced or rejected depending on Jackson's coercion settings,
  and either way would introduce a second spelling of the same flag.
* **Milliseconds, in both time fields.** The original producer sent
  ``timePeriod`` in seconds next to a millisecond ``startTime``, so the engine
  compared a seconds value against ``event.fall.threshold.value``. The unit is
  in the attribute names here so the mismatch cannot recur.
* **``confidence`` is a fraction in [0, 1]** despite the wire key being
  ``confidencePercentage``. The name is the engine's; the dashboard is what
  multiplies by 100 for display (``web/src/pages/Reporting.js``).

Events are validated on construction because there is no later opportunity: an
invalid one surfaces as a NullPointerException in the engine's listener thread,
which drops the message, or as a plausible-looking wrong number on a chart.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


# UP042 suggests `enum.StrEnum`, which would behave identically everywhere this
# module uses the type. The base class stays as it is because it is part of the
# frozen public signature, and swapping it changes `str()` and `format()` of
# every member for every caller -- not a lint-level edit.
class EventType(str, Enum):  # noqa: UP042
    """The event names the engine accepts, mirroring ``EventNameEnum.java``.

    A ``str`` subclass because the engine compares ``eventType`` against
    ``EventNameEnum.<name>()`` as a plain string, and because it keeps every
    string-keyed lookup on this side working against a bare ``"FALL"``.
    """

    FALL = "FALL"
    ARMS_UP = "ARMS_UP"
    FRONT_BEND = "FRONT_BEND"
    NO_HELMET = "NO_HELMET"
    NO_JACKET = "NO_JACKET"

    @property
    def is_periodic(self) -> bool:
        """Whether this event describes a violation that lasts for a window.

        Periodic events carry a duration and are aggregated by summing it per
        day (``/event/periodic-events``); countable events are aggregated by
        counting occurrences per day. This is the same split
        ``RawEventService.listener`` branches on.
        """
        return self in (EventType.NO_HELMET, EventType.NO_JACKET)


@dataclass(frozen=True, slots=True)
class DetectionEvent:
    """A single safety event, ready to publish.

    Frozen and hashable so that buffered events can be de-duplicated by set
    membership before they reach the broker.
    """

    event_type: EventType
    start_time_ms: int
    confidence: float
    camera_name: str
    time_period_ms: int | None = None

    def __post_init__(self) -> None:
        # `Long startTime` on the Java side, and Jackson truncates a float into
        # it silently (ACCEPT_FLOAT_AS_INT is on by default).
        if not isinstance(self.start_time_ms, int):
            raise TypeError(
                "start_time_ms must be an int of milliseconds since the epoch, got "
                f"{type(self.start_time_ms).__name__}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must lie within [0.0, 1.0], got {self.confidence!r}")

        if self.event_type.is_periodic:
            if self.time_period_ms is None:
                raise ValueError(
                    f"{self.event_type.value} is a periodic event and requires time_period_ms; "
                    "the engine reads the duration of every periodic event"
                )
            if self.time_period_ms < 0:
                raise ValueError(
                    f"time_period_ms must not be negative, got {self.time_period_ms}"
                )
        elif self.time_period_ms is not None:
            raise ValueError(
                f"{self.event_type.value} is a countable event and must not carry "
                f"time_period_ms, got {self.time_period_ms}"
            )

    def to_json(self) -> bytes:
        """Serialise to the UTF-8 JSON bytes expected on the ``rawEvents`` topic.

        Bytes rather than ``str`` because that is what ``KafkaProducer.send``
        takes; a ``str`` fails at send time, on site.
        """
        payload = {
            "cameraName": self.camera_name,
            "confidencePercentage": self.confidence,
            "eventType": self.event_type.value,
            "isProcessed": "false",
            "timePeriod": self.time_period_ms,
            "startTime": self.start_time_ms,
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")
