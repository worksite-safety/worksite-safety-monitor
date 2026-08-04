# Baseline trace — provenance and coverage

`trace.jsonl.gz` records what the two YOLO models actually saw on a real
worksite clip. It exists so the rewritten detector can be compared against the
original `aiModule.py` logic on identical input, and every behaviour change
shown to be intentional rather than accidental.

## How it was produced

```
detector/tools/capture_trace.py \
  --video worksite-clip.mp4 \
  --pose-model yolov8s-pose.pt --ppe-model best.pt \
  --out detector/tests/data/baseline/trace.jsonl.gz
```

| | |
|---|---|
| Source clip | `Baumit İnşaat Alanı.mp4`, 1080×1920, 30 fps, 986 frames, 32.8 s |
| Pose model | `yolov8s-pose.pt`, `conf=0.8` — matches `aiModule.py:291` |
| PPE model | `best.pt`, `conf=0.6` — matches `aiModule.py:293` |
| ultralytics | 8.3.253 |
| torch | 2.13.0+cpu (no CUDA) |
| Captured | 2026-08-04 |
| Size | 457 KB gzipped |

The clip is **not** committed — only the trace. The trace holds model *outputs*
(keypoints, confidences, boxes), never pixels, so it is small, deterministic and
replayable without weights, a camera or a GPU.

Note the models are the current ultralytics release, not the 8.0.x the original
code required (`from ultralytics.yolo.utils.plotting import ...`, a path removed
in 8.1). The original file therefore cannot be executed at all today. Stage B
below transcribes its logic instead of running it.

## What the trace contains

| | |
|---|---|
| Frames | 986 |
| Frames with at least one person | 708 |
| Frames with **no** person | **278**, in 31 blocks, longest 4233 ms |
| Person detections | 1114 (≈1.6 per populated frame) |
| Max people in one frame | **4** |
| `no-jacket` detections | 74, across 63 frames |
| `fall` detections | 19, between 15733 ms and 25800 ms |
| `no-helmet` detections | **0** |

## What this trace CAN prove

- **Bug #1 — `NO_JACKET` is never published.** 63 frames carry the detection;
  the transcribed original logic emits zero events. This is the headline
  regression proof.
- **Bug #9 — preview freezes on person-free frames.** 278 such frames in 31
  separate blocks.
- **Bug #10 — `timePeriod` unit.** Any emitted periodic event exercises it.
- **Bugs #5/#7 — confidence is keypoint visibility, not detection confidence.**
  Both values are in the trace, so the swap is directly observable.
- **FALL throttling.** 19 detections spanning 10 s; the 3-minute cooldown must
  collapse them to exactly one event.
- **Multi-person state.** Up to 4 simultaneous people, so per-person state is
  genuinely exercised — just not to the point of overflow.

## What this trace CANNOT prove — must be covered by synthetic unit tests

Stated plainly so nobody mistakes a green differential for full coverage.

- **`NO_HELMET` — no data at all.** The clip contains zero `no-helmet`
  detections. Every helmet-related assertion is synthetic.
- **Bug #3 — `IndexError` with 10+ people.** Maximum here is 4. The fixed-size
  `[0]*10` arrays never overflow on this footage.
- **Bug #2 — `numberOfPerson` is always 17.** Visible in the trace only
  indirectly; the fix is pinned by unit tests.
- **Bug #15 — violation window never closes when the person leaves frame.** The
  exact transition (an open `no-jacket` window followed immediately by a
  person-free frame) does not occur here.
- **Bug #16 — one-sided visibility poisons the averaged angle.** Present in the
  keypoint confidences, but isolating it needs constructed input.
- Model accuracy, camera I/O, Kafka wire compatibility, throughput.

## An empirical finding that shaped the design

The `no-jacket` detections are heavily fragmented — 63 frames spread over 27
runs, the longest only 367 ms. Measured against the engine's 3-second periodic
threshold:

| `grace_ms` | windows | windows over 3 s |
|---|---|---|
| 0 (original behaviour) | 63 | **0** |
| 500 | 7 | 1 |
| 1000 | 6 | 1 |
| **1500 (chosen default)** | **4** | **1, of 6500 ms** |
| 2000 | 4 | 1 |

Without a grace period, fixing bug #1 alone would still have recorded *nothing*:
every window falls under the threshold and the engine drops it. With
`grace_ms=1500` the same footage yields one coherent 6.5-second jacket
violation. The grace window is not a refinement — on this footage it is the
difference between the feature working and not working.

`grace_ms=1500` sits at the knee: 1000 already collapses the run, and 2000 buys
nothing further.
