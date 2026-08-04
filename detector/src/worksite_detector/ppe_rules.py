"""Violation windows for the periodic PPE events, and the FALL send throttle.

``NO_HELMET`` and ``NO_JACKET`` are periodic events: each one carries a duration,
and ``RawEventService.listener`` stores it only if that duration is *strictly*
over ``event.fall.threshold.value`` (3000 ms). One event therefore has to span
many frames, and the only question this module answers is where a violation
begins and where it ends.

**A violation window** is that span. It opens on the first frame reporting a
violating type, absorbs every later frame reporting the same type, and closes
once the type has been absent for ``grace_ms``. Closing is what emits the single
``DetectionEvent`` for the window; while it is open nothing is published, because
nothing is yet known about its duration. Windows are held per event type and are
entirely independent -- a helmet violation neither closes nor extends a jacket
one. The original kept two asymmetric sets of ad-hoc flags instead, which is how
``NO_JACKET`` could be dead for the life of the project while ``NO_HELMET``
worked.

**Why the window closes on a grace timer rather than on the first clean frame.**
Detections flicker. ``tests/data/baseline/PROVENANCE.md`` measures it on 986
frames of real footage: the 63 ``no-jacket`` frames arrive as 27 separate runs,
the longest 367 ms. Closing on the first clean frame yields 63 windows and *zero*
over the engine's 3-second threshold, so every one of them is dropped downstream
in silence -- fixing the never-published bug alone would still have recorded
nothing. Merging across gaps shorter than 1500 ms turns the same footage into one
coherent 6500 ms violation. 500 ms already collapses the run to 7 windows and
2000 ms buys nothing further, so the default sits at the knee of that sweep. The
grace period is not a refinement to be simplified away later; on this footage it
is the difference between the feature working and not working.

**What ``time_period_ms`` measures**: the last violating frame minus the first,
in milliseconds. It is what was *observed*, so it never includes the grace period
that closed the window and never runs to the wall-clock moment of the close. A
100 ms violation reports 100, not 1600 -- otherwise the grace tolerance would
itself push sub-threshold flicker over the engine's gate. For the same reason a
window closed at shutdown is measured to its last frame and not to the shutdown
instant: a slow teardown must not inflate a duration. A violation seen on exactly
one frame reports 0 ms and is still emitted; discarding short violations is the
engine's job, and a second silent filter here would be undiagnosable.

Gaps longer than the grace are never bridged, with or without an intervening
clean frame. ``observe`` runs once per frame, so a five-second gap between two
violating frames means the tracker was told nothing for five seconds; claiming
the violation persisted through them would invent an unobserved duration, which
is the defect class this module exists to remove.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from worksite_detector.events import DetectionEvent, EventType


@dataclass(slots=True)
class _Window:
    """One violation in progress: its extent so far and its confidence samples.

    The sum and count are per window rather than per tracker: the reported
    confidence is the mean over the samples that produced *this* violation. The
    original accumulated both for the life of the process, so every event after
    the first reported a session-long running mean.
    """

    started_ms: int
    last_seen_ms: int
    confidence_sum: float
    sample_count: int


class PpeViolationTracker:
    """Turns per-frame PPE detections into one event per violation window.

    Feed every frame to ``observe``, including the clean ones -- a clean frame is
    what eventually closes a window, and a frame with no person in it is clean.
    The original skipped its whole emit block when the pose model found nobody,
    so a violation that ended by the worker walking out of shot stayed open and
    was later published with an absurd duration.

    One instance per camera. The state is mutable and unsynchronised, matching
    the single-threaded frame loop that owns it.
    """

    def __init__(
        self,
        camera_name: str,
        grace_ms: int = 1500,
        tracked: Sequence[EventType] = (EventType.NO_HELMET, EventType.NO_JACKET),
    ) -> None:
        """Configure a tracker.

        ``camera_name`` is published verbatim and is how the dashboard attributes
        a violation to a site. ``grace_ms`` is the silence that closes a window;
        see the module docstring for how the default was measured. ``tracked``
        fixes both which types have windows and the order ``flush`` emits them
        in, so a shutdown batch does not vary with which window opened first.

        Raises:
            ValueError: If ``grace_ms`` is negative, or if ``tracked`` holds a
                countable event type.
        """
        if grace_ms < 0:
            # A negative grace inverts `elapsed >= grace_ms` into a condition that
            # holds on the frame after a window opens, so every window would close
            # immediately instead of failing visibly.
            raise ValueError(f"grace_ms must not be negative, got {grace_ms}")

        countable = [event_type.value for event_type in tracked if not event_type.is_periodic]
        if countable:
            raise ValueError(
                f"tracked must hold periodic event types only, got {countable}. Countable "
                "events have no duration and no window; they are published as they occur."
            )

        self._camera_name = camera_name
        self._grace_ms = grace_ms
        self._tracked = tuple(tracked)
        self._open: dict[EventType, _Window] = {}

    def observe(
        self, frame_time_ms: int, violations: Mapping[EventType, float]
    ) -> list[DetectionEvent]:
        """Record one frame and return the windows it closed, if any.

        ``violations`` maps each type violated on this frame to the detector's
        confidence in it, as a fraction in [0, 1]; an empty mapping is a clean
        frame. There is one entry per type, not per person, so three bare-headed
        workers are one ``NO_HELMET`` window -- per-person attribution would need
        an identity the pose stage does not produce.

        Most frames return an empty list. A frame returns an event when a window's
        grace has elapsed, whether the frame is clean or has reopened the same
        violation after too long a gap.

        Calling this twice for one ``frame_time_ms`` counts that confidence sample
        twice and biases the window's mean. That is a caller bug -- the pipeline
        calls this once per frame -- and it is deliberately not guarded: raising
        inside a real-time frame loop over a marginally skewed mean is the worse
        of the two outcomes.

        Raises:
            ValueError: If ``violations`` names a type outside ``tracked``, or
                carries a confidence outside [0, 1]. Both are refused before any
                state changes, so the traceback points at the offending frame: a
                bad sample averaged against good ones lands back inside [0, 1] and
                reaches the dashboard as a plausible wrong percentage, and a type
                dropped in silence here is how ``NO_JACKET`` went missing.
        """
        for event_type, confidence in violations.items():
            if event_type not in self._tracked:
                raise ValueError(
                    f"{event_type.value} is not tracked by this instance "
                    f"({', '.join(member.value for member in self._tracked)}); routing it "
                    "here is a wiring error, and ignoring it would lose the detection."
                )
            if not 0.0 <= confidence <= 1.0:
                raise ValueError(
                    f"confidence for {event_type.value} must lie within [0.0, 1.0], got "
                    f"{confidence!r}. It is a fraction here; the web layer multiplies by 100."
                )

        emitted: list[DetectionEvent] = []
        for event_type in self._tracked:
            window = self._open.get(event_type)
            if window is not None and frame_time_ms - window.last_seen_ms >= self._grace_ms:
                emitted.append(self._close(event_type))
                window = None

            if event_type in violations:
                if window is None:
                    self._open[event_type] = _Window(
                        started_ms=frame_time_ms,
                        last_seen_ms=frame_time_ms,
                        confidence_sum=violations[event_type],
                        sample_count=1,
                    )
                else:
                    window.last_seen_ms = frame_time_ms
                    window.confidence_sum += violations[event_type]
                    window.sample_count += 1

        return emitted

    def flush(self, now_ms: int) -> list[DetectionEvent]:
        """Close every open window, in ``tracked`` order, and return the events.

        For shutdown, where a violation still in progress would otherwise be lost
        -- the original ran nothing after its frame loop. Idempotent, because
        shutdown paths routinely run twice (a signal handler and a ``finally``).

        ``now_ms`` completes the symmetry with ``observe`` and is deliberately not
        used to measure anything: every window is closed regardless of how much of
        its grace has elapsed, and each is measured to its own last observed frame
        so that a slow teardown cannot stretch a duration.
        """
        return [
            self._close(event_type) for event_type in self._tracked if event_type in self._open
        ]

    def _close(self, event_type: EventType) -> DetectionEvent:
        """Remove the open window for ``event_type`` and build its event."""
        window = self._open.pop(event_type)
        return DetectionEvent(
            event_type=event_type,
            # Where the violation began, not where it was noticed to have ended:
            # the dashboard buckets by this field, and a close-time value lands an
            # event in the wrong day near midnight.
            start_time_ms=window.started_ms,
            confidence=window.confidence_sum / window.sample_count,
            camera_name=self._camera_name,
            # Clamped because camera clock skew and frame reordering both run
            # backwards. A negative duration raises out of DetectionEvent and takes
            # the frame loop with it; zero is the honest reading of a window whose
            # frames arrived out of order.
            time_period_ms=max(0, window.last_seen_ms - window.started_ms),
        )


class FallThrottle:
    """Rate-limits FALL events to one per cooldown.

    A single fall is detected on many consecutive frames -- 19 times over ten
    seconds on the baseline clip -- and every one that reaches the engine emails
    *every* user in the database.

    One instance per camera. The original held its reference time in a loop
    variable, so a second camera in the same process would have shared it and
    swallowed the other camera's falls.
    """

    def __init__(self, cooldown_ms: int) -> None:
        """Configure the throttle.

        Raises:
            ValueError: If ``cooldown_ms`` is negative, which would re-arm the
                throttle in the past and let every detection through.
        """
        if cooldown_ms < 0:
            raise ValueError(f"cooldown_ms must not be negative, got {cooldown_ms}")

        self._cooldown_ms = cooldown_ms
        # None is "never fired", and it is not interchangeable with an initial
        # reference of `-cooldown_ms` -- the literal port of the original's
        # `datetime.now() - timedelta(minutes=3)`. At cooldown 0 that offset starts
        # the reference at 0 and the strictly-greater-than test denies the very
        # first fall of the session. The first fall must always pass, whatever the
        # cooldown, so the absence of a previous send has to be its own state
        # rather than a timestamp chosen to imitate one.
        self._last_allowed_ms: int | None = None

    def allow(self, now_ms: int) -> bool:
        """Whether a FALL detected at ``now_ms`` should be published, re-arming if so.

        The boundary is strictly greater than, matching the original: the cooldown
        instant itself is still suppressed, the millisecond after it is not.

        A suppressed detection leaves the cooldown where it was. Extending it on
        every attempt would turn one fall's burst of detections into a rolling
        block that also suppresses the *next*, genuinely new fall.
        """
        if (
            self._last_allowed_ms is not None
            and now_ms <= self._last_allowed_ms + self._cooldown_ms
        ):
            return False

        self._last_allowed_ms = now_ms
        return True
