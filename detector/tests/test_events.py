"""The wire contract for `worksite_detector.events`: the JSON that reaches the engine.

`RawEvent` is annotated `@JsonIgnoreProperties(ignoreUnknown = true)`, so a key this
producer misspells is dropped in silence — no exception, no log line, just an empty
column in MongoDB and a gap in the dashboard. Nothing downstream catches it. That is
why the key set below is asserted against the Java source itself rather than against a
copy of it: the two modules are built and released separately, and a regex over
`RawEvent.java` is the only link that breaks when either side drifts.

The Java files live outside this package, so these tests fail loudly if the checkout is
partial rather than passing vacuously.
"""
from __future__ import annotations

import json
import re
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
from worksite_detector.events import DetectionEvent, EventType

ENGINE_MODEL = (
    Path(__file__).resolve().parents[2]
    / "engine" / "src" / "main" / "java" / "com" / "graduation" / "project" / "engine"
)
RAW_EVENT_JAVA = ENGINE_MODEL / "rawEvent" / "model" / "RawEvent.java"
EVENT_NAME_ENUM_JAVA = ENGINE_MODEL / "event" / "model" / "EventNameEnum.java"

# The only six keys the engine can read. Transcribed from RawEvent.java for test 4;
# test 5 re-derives them from the Java source so this literal cannot rot unnoticed.
JAVA_FIELD_NAMES = {
    "cameraName",
    "confidencePercentage",
    "eventType",
    "isProcessed",
    "startTime",
    "timePeriod",
}

COUNTABLE_KWARGS: dict[str, Any] = {
    "event_type": EventType.FALL,
    "start_time_ms": 1_700_000_000_000,
    "confidence": 0.87,
    "camera_name": "cam-1",
}
PERIODIC_KWARGS: dict[str, Any] = {
    "event_type": EventType.NO_HELMET,
    "start_time_ms": 1_700_000_000_000,
    "confidence": 0.87,
    "camera_name": "cam-1",
    "time_period_ms": 4_500,
}


def _event(**overrides: Any) -> DetectionEvent:
    """A valid countable event, with fields replaced so each test shows only what it varies."""
    return DetectionEvent(**{**COUNTABLE_KWARGS, **overrides})


def _payload(event: DetectionEvent) -> dict[str, Any]:
    return json.loads(event.to_json())


def _java_source(path: Path) -> str:
    assert path.is_file(), (
        f"{path} not found — the cross-module contract tests must not pass vacuously"
    )
    return path.read_text(encoding="utf-8")


def _engine_enum_constants() -> set[str]:
    """The constants declared in EventNameEnum.java."""
    body = re.search(
        r"\benum\s+EventNameEnum\s*\{(.*?)\}", _java_source(EVENT_NAME_ENUM_JAVA), re.S
    )
    assert body is not None, "could not locate the EventNameEnum body in the Java source"
    constants = set(re.findall(r"\b([A-Z][A-Z0-9_]+)\b", body.group(1)))
    assert len(constants) == 5, f"parsed {sorted(constants)} from EventNameEnum.java, expected 5"
    return constants


def _raw_event_field_names() -> set[str]:
    """The private field names declared in RawEvent.java, i.e. the JSON keys Jackson binds."""
    fields = set(re.findall(r"private\s+[\w.<>\[\]]+\s+(\w+)\s*;", _java_source(RAW_EVENT_JAVA)))
    assert len(fields) == 6, f"parsed {sorted(fields)} from RawEvent.java, expected 6"
    return fields


# --------------------------------------------------------------------------- enum


def test_event_type_values_match_engine_enum() -> None:
    # Parsed, not hardcoded: a rename on either side must fail here, because the engine
    # compares eventType by string and an unknown value is dropped without an error.
    assert {member.value for member in EventType} == _engine_enum_constants()


def test_event_type_is_str_subclass() -> None:
    # A bare Enum compares False against "FALL", which would silently disable every
    # string-keyed lookup and every `== "FALL"` guard in the pipeline.
    assert EventType.FALL == "FALL"


@pytest.mark.parametrize(
    ("event_type", "is_periodic"),
    [
        (EventType.NO_HELMET, True),
        (EventType.NO_JACKET, True),
        (EventType.FALL, False),
        (EventType.ARMS_UP, False),
        (EventType.FRONT_BEND, False),
    ],
    ids=lambda param: param.name if isinstance(param, EventType) else str(param),
)
def test_periodic_classification(event_type: EventType, is_periodic: bool) -> None:
    # RawEventService.listener branches on exactly this split, and only the periodic
    # branch reads timePeriod; misclassifying an event silently changes how it is stored.
    assert event_type.is_periodic is is_periodic


# --------------------------------------------------------------------- json contract


@pytest.mark.parametrize(
    "kwargs", [COUNTABLE_KWARGS, PERIODIC_KWARGS], ids=["countable", "periodic"]
)
def test_to_json_key_set_is_exactly_the_java_field_names(kwargs: dict[str, Any]) -> None:
    # An extra key is dead weight and a missing key is a null column; @JsonIgnoreProperties
    # (ignoreUnknown = true) raises for neither. The set is invariant across both families.
    assert set(_payload(DetectionEvent(**kwargs))) == JAVA_FIELD_NAMES


def test_json_field_names_match_rawevent_java_source() -> None:
    # The live cross-module contract: this breaks the moment RawEvent.java gains, loses
    # or renames a field, which is the failure mode Jackson is configured to hide.
    assert set(_payload(_event())) == _raw_event_field_names()


def test_to_json_periodic_time_period_is_milliseconds() -> None:
    # pins bug #10: timePeriod was seconds while startTime was millis (aiModule.py:467),
    # so the engine compared a seconds value against its threshold.
    event = _event(event_type=EventType.NO_HELMET, time_period_ms=4_500)
    assert _payload(event)["timePeriod"] == 4_500


def test_to_json_returns_utf8_bytes() -> None:
    # KafkaProducer takes bytes; a str is rejected at send() time on site, not here. Turkish
    # camera names are the norm on this deployment, so the encoding is not incidental.
    raw = _event(camera_name="kamera-üst").to_json()
    assert isinstance(raw, bytes)
    assert json.loads(raw.decode("utf-8"))["cameraName"] == "kamera-üst"


def test_event_type_serialises_as_bare_string() -> None:
    # str(EventType.NO_HELMET) is "EventType.NO_HELMET"; the engine compares against
    # EventNameEnum.NO_HELMET.name(), so an f-string here loses the event without a trace.
    event = _event(event_type=EventType.NO_HELMET, time_period_ms=1_000)
    assert _payload(event)["eventType"] == "NO_HELMET"


# ---------------------------------------------------------------------- validation


def test_periodic_event_without_time_period_is_rejected() -> None:
    # The engine calls data.getTimePeriod().intValue() on periodic events: a null is an NPE
    # in the listener thread, and the message is lost with no signal back to the producer.
    with pytest.raises(ValueError):
        _event(event_type=EventType.NO_HELMET, time_period_ms=None)


def test_countable_event_with_time_period_is_rejected() -> None:
    # A FALL carrying a duration is a category error: /event/periodic-events sums durations
    # only for the periodic family, so the value would be accepted and never read.
    with pytest.raises(ValueError):
        _event(event_type=EventType.FALL, time_period_ms=5)


@pytest.mark.parametrize(
    ("confidence", "accepted"),
    [(-0.1, False), (1.5, False), (0.0, True), (1.0, True)],
)
def test_confidence_bounds(confidence: float, accepted: bool) -> None:
    # pins bugs #5/#7: the original sent keypoint visibility instead of detection
    # confidence, unconstrained, so near-zero garbage reached the dashboard as a percentage.
    if accepted:
        assert _event(confidence=confidence).confidence == confidence
    else:
        with pytest.raises(ValueError):
            _event(confidence=confidence)


def test_negative_time_period_rejected() -> None:
    # A negative window means the clock ran backwards; the engine's `> threshold` check
    # would quietly drop it, hiding the arithmetic fault that produced it.
    with pytest.raises(ValueError):
        _event(event_type=EventType.NO_HELMET, time_period_ms=-1)


def test_start_time_ms_must_be_int() -> None:
    # The Java field is `Long startTime`. Jackson coerces a float to Long by truncation
    # (ACCEPT_FLOAT_AS_INT is on by default), so a wrong-typed clock lands in Mongo unflagged.
    with pytest.raises((TypeError, ValueError)):
        _event(start_time_ms=1.7e12)


# ----------------------------------------------------------------- object semantics


def test_is_frozen_and_hashable() -> None:
    # Events are buffered and de-duplicated by set membership before publication; a mutable
    # or unhashable event silently defeats both.
    event = _event()
    twin = _event()
    with pytest.raises(FrozenInstanceError):
        event.confidence = 0.5  # type: ignore[misc]
    assert event == twin
    assert hash(event) == hash(twin)
