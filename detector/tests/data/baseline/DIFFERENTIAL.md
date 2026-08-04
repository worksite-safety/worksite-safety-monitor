# Baseline differential — what the rewrite changed, measured

Both implementations were driven over the **same 986 trace records**, in the same order,
from one in-memory list:

* **old** — `legacy_oracle.replay(records)`, the transcription of `aiModule.py` lines
  312–512 with the producer and the two clock reads substituted out, frozen in
  `baseline_events.jsonl`.
* **new** — the real `worksite_detector.pipeline.Pipeline` with `GestureDetector`,
  `PpeViolationTracker`, `FallThrottle` and `InMemoryEventPublisher`, wired from `Config()`
  defaults. The only doubles are the frame source, the two models, the sink, and a
  delegating spy on the gesture detector. The models read the trace record back out of
  `frame.image`, so the record they project **is** the record the oracle read.

Reproduce with `..\.venv\Scripts\python.exe -m pytest tests/test_baseline_differential.py`
from `detector/`. 19 tests, 0.09 s: 20 ms to parse the trace, 3 ms for the legacy replay,
11 ms for the pipeline. The suite goes from 307 to 326 tests and from 0.39 s to 0.41 s.

## The table

| event type | old | new | one-line reason |
|---|---:|---:|---|
| `FALL` | 1 | 1 | **count unchanged, incident moved**: 24066 ms → 15733 ms |
| `ARMS_UP` | 0 | 0 | the footage contains no completed arm raise |
| `FRONT_BEND` | 0 | 0 | the footage contains no bend |
| `NO_HELMET` | 0 | 0 | the trace holds zero `no-helmet` detections — no evidence either way |
| `NO_JACKET` | 0 | 4 | bug #1: `controlJacket` was never set True, so the emit was unreachable |
| **total** | **1** | **5** | |

Frames reaching the end of the pipeline: **986 of 986** (new) against **708 of 986** (old) —
the 278 person-free frames the `continue` at line 310 skipped whole.

## NO_JACKET — 0 → 4

63 frames carry a `no-jacket` detection, in 27 runs, the longest 367 ms. The old code
published none of them, on any input: `controlJacket` is set `False` at line 409 and set
`False` again at 428 where `True` was meant, so the block at 489 is dead.

The four windows the rewrite emits, `(frame, start_time_ms, time_period_ms, confidence)`:

| frame | start | duration | confidence |
|---:|---:|---:|---:|
| 395 | 11666 | 0 ms | 0.6410783529281616 |
| 492 | 14700 | 200 ms | 0.667099729180336 |
| 563 | 17233 | 33 ms | 0.6446486711502075 |
| 956 | 23866 | **6500 ms** | 0.6560190383877073 |

Confidence is the mean over each window's own samples, inside the trace's `no-jacket`
detection range of 0.6015–0.7453. The old code's formula was `sumJacket / numJacket`, never
reset, i.e. a session-long running mean.

**The grace window is what makes the fix real.** Measured on this trace:

| `grace_ms` | windows | over 3000 ms | longest |
|---:|---:|---:|---:|
| 0 | 63 | 0 | 0 ms |
| 500 | 8 | 0 | 2934 ms |
| 1000 | 6 | 1 | 3967 ms |
| **1500** | **4** | **1** | **6500 ms** |
| 2000 | 4 | 1 | 6500 ms |

Fixing bug #1 alone, with windows closing on the first clean frame, would have recorded
**nothing**: the engine stores a periodic event only above its threshold, and no window
clears it.

> **Correction.** The `500` row above disagrees with the sweep published in `PROVENANCE.md`
> and repeated in the `ppe_rules` module docstring, both of which say *7 windows, 1 over
> 3 s*. Driving `PpeViolationTracker` itself over the trace gives **8 windows, none over
> 3 s**, longest 2934 ms; every other row matches exactly. The conclusion the sweep was
> drawn for is unaffected and slightly strengthened — 500 ms records nothing at all, 1000 ms
> is the first setting that records anything, 1500 ms is where the run becomes one coherent
> violation. `test_grace_sweep_on_this_trace_and_one_row_of_PROVENANCE_is_wrong` pins the
> measured numbers; the frozen provenance document was left as it is.

## FALL — 1 → 1, and 8333 ms earlier

Not the expected 1 → 2. The trace holds 19 `fall` detections between 15733 ms and 25800 ms.

| | old | new |
|---|---|---|
| published | 1 | 1 |
| frame / start | 722 / 24066 ms | 472 / **15733 ms** |
| confidence | 0.7161806225776672 | 0.7386404275894165 |
| suppressed detections | 17 (of the 18 it could see) | 18 |

Frame 472 is the **only one of the 19 fall frames with no detectable person**, so line 310
skipped it and the old code's first reachable fall was the 24066 ms one. The rewrite sees
it and publishes it — and `FallThrottle`, at the original's own `timedelta(minutes=3)`
(180000 ms), then suppresses everything through 195733 ms, which includes 24066.

The clip is 32833 ms long. **No configuration of this code publishes both falls**, because
the cooldown outlives the whole recording. The rewrite reports the earlier incident 8.3 s
sooner; it does not report one more of them. Whether 15733 and 24066 are one fall or two is
a question this trace cannot answer.

## ARMS_UP and FRONT_BEND — 0 → 0

The old code emitted zero because its latch armed once per slot and never re-armed. The
rewrite's latch does re-arm, and it still emits zero — because the gesture is not in the
footage. Measured over all 1114 person-frames, after the rewrite's own gates:

| gesture | decisions | angle range | band | why nothing fires |
|---|---:|---|---|---|
| `ARMS_UP` | 964 | 0.1° – **121.5°** | arms < 30, completes > 140 | 551 frames arm; the angle never reaches 140, so no cycle ever completes |
| `FRONT_BEND` | 330 | **156.4°** – 179.6° | arms < 130, completes > 160 | the angle never falls below 130, so no cycle ever starts |

The old code's angles on the same frames are within 0.4° of these (armsUp 0.5–121.5,
bending 156.4–179.6): **the trace contains zero `(0, 0)` keypoint sentinels** — ultralytics
8.3 emits real coordinates with a low confidence instead — so bug #16, the one-sided
average, is not exercised here at all and the two angle computations coincide.

Visibility gates passing 964 and 811 times means a limb was *seen*, not that a gesture
*happened*. Every gesture assertion in this project stays synthetic; this trace promotes
none of them.

The rewrite's gates are still measurably stricter where it matters: FRONT_BEND's gate now
covers the ankles it measures the posture from, cutting 811 legacy gate passes to 601 left /
614 right side passes, of which the upright precondition rejects 285, leaving 330 decisions.

## Confidence — keypoint visibility → detection confidence

The trace holds both populations: 18808 distinct per-keypoint visibility scores and 93
distinct PPE-model detection confidences, **with no value in common**.

Neither run publishes a gesture here, so the swap cannot be read off the events. It is read
off the value that reaches the rule: the pipeline handed `GestureDetector` all 1114
person-box confidences, in model order, exactly equal to the trace's `box_conf` column —
while `row[7]` (left elbow, what the old ARMS_UP published) and `row[11]` (left hip, what
the old FRONT_BEND published) differ from the box confidence on **every one** of the 1114
person-frames.

Every confidence the new run did publish is a detection confidence: FALL verbatim, NO_JACKET
as a window mean. None appears among the keypoint visibilities.

## timePeriod — seconds → milliseconds, and an engine-side gap

The old payload sent `int(elapsed_seconds)` next to a millisecond `startTime`. Applied to
the four windows above, that formula yields `[0, 0, 0, 6]`: three collapse to zero and the
survivor loses 500 ms.

**The consumer has not been retuned.** `RawEventService.listener` compares
`data.getTimePeriod().intValue() > fallEventThreshold`, and
`engine/src/main/resources/application.yml` sets `event.fall.threshold.value: 3` — correct
as *3 seconds* while the producer sent seconds, but now read against milliseconds:

* intended (`> 3000 ms`): **1** of the 4 windows stored — the 6500 ms one.
* as deployed (`> 3`): **3** of the 4 stored — including a 33 ms flicker.

Both readings are asserted in `test_at_least_one_no_jacket_window_clears_the_engine_threshold`
so the gap cannot close by accident. Changing the engine property to `3000` is the matching
half of this fix and has not been made.

## What this differential does not cover

Restating `PROVENANCE.md` against measured results rather than expectations:

* **`NO_HELMET`** — zero detections in the clip. Both runs emitting zero proves nothing.
* **Both gestures** — no completed gesture in the clip; the re-arming latch is unexercised.
* **Bug #16** — zero `(0, 0)` sentinels in the trace; the one-sided average never fires.
* **Bug #3** — maximum 4 people in a frame, so the `[0]*10` arrays never overflow.
* **Bug #15** — no open jacket window is followed immediately by a person-free frame.
* **The shutdown flush** — no window was open at the end of the clip, so nothing was
  emitted after the last frame and the injected clock never reached a published field.
