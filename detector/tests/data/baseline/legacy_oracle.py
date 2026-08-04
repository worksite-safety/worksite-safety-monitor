"""Stage B of the baseline: a line-by-line transcription of the ORIGINAL rule logic.

This file reproduces `detector/aiModule.py` lines 312-512 (the per-frame rule
logic) so that the rewritten detector can be diffed against what the original
code *actually did* on identical input. It is an oracle, not a design: every
defect is preserved deliberately. Do not "fix" anything in here -- a fix makes
the differential test lie.

The original cannot be executed today: it does
`from ultralytics.yolo.utils.plotting import ...`, a module path removed in
ultralytics 8.1 (installed: 8.3.253). Hence transcription rather than a run.

Exactly three substitutions were applied, and no others:

  1. `producer.send('rawEvents', ...)` / `producer.flush()`
     -> append `prediction_data` to the `emitted` list.
  2. `time.time()`      -> `frame["timestamp_ms"] / 1000.0` of the current frame.
  3. `datetime.now()`   -> `datetime.fromtimestamp(frame["timestamp_ms"] / 1000.0)`.

Every structural deviation forced by the trace format (plain lists where the
original had torch tensors) is flagged with a `# DEVIATION:` comment stating why
it cannot change behaviour. Every defect that survives on purpose is flagged
with `# NOTE:`.

Line references in comments are line numbers in the original `aiModule.py`.
"""
# ruff: noqa
# ^ Deliberate. Every lint this file trips is load-bearing transcription fidelity:
#   E501  the unparenthesised `and`/`or` visibility conditions (aiModule.py:321,
#         358) are reproduced on one line, as written.
#   SIM102 the nested `if visibility: / if angle > 160:` is the original's shape.
#   B905  `zip()` without `strict=` -- adding strict would make mismatched
#         box/class/conf lengths raise where the original silently truncated.
#   F841  `message` / `key` are the arguments the removed `producer.send` took;
#         they are kept so the payload is still JSON-serialised on every path.
from __future__ import annotations

import json
import math
from collections.abc import Iterable
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# aiModule.py lines 20-45 -- transcribed unchanged.
# ---------------------------------------------------------------------------
# NOTE: 'frontbending' is dead configuration. FRONT_BEND events are computed
#       from the 'bending' entry, because `Args2.sport == 'bending'` and line
#       324/325 read `sport_list[args.sport]`. Nothing ever reads 'frontbending'.
# NOTE: 'frontbending' also indexes keypoints 3 and 4 (the ears), which is
#       anatomically meaningless for a bend angle -- further evidence it was
#       abandoned rather than used.
sport_list = {
    'armsUp': {
        'left_points_idx': [11, 5, 7],
        'right_points_idx': [12, 6, 8],
        'maintaining': 30,
        'relaxing': 140,
        'concerned_key_points_idx': [5, 6, 7, 8, 11, 12],
        'concerned_skeletons_idx': [[12, 6], [6, 8], [11, 5], [5, 7]]
    },
    'bending': {
        'left_points_idx': [5, 11, 13],
        'right_points_idx': [6, 12, 14],
        'maintaining': 130,
        'relaxing': 160,
        'concerned_key_points_idx': [5, 6, 11, 12, 13, 14],
        'concerned_skeletons_idx': [[14, 12], [12, 6], [13, 11], [11, 5]]
    },
    'frontbending': {
        'left_points_idx': [3, 11, 13],
        'right_points_idx': [4, 12, 14],
        'maintaining': 130,
        'relaxing': 160,
        'concerned_key_points_idx': [3, 4, 11, 12, 13, 14],
        'concerned_skeletons_idx': [[14, 12], [12, 4], [13, 11], [11, 3]]
    }
}


# ---------------------------------------------------------------------------
# aiModule.py lines 48-88 -- arithmetic transcribed unchanged.
# ---------------------------------------------------------------------------
def calculate_angle(key_points, left_points_idx, right_points_idx):
    """Original signature took an ultralytics `Keypoints` object and read
    `key_points.data[0][i][0]` / `[1]`, then `.item()`'d the float32 scalars.

    DEVIATION: `key_points` here is a plain list of 17 `[x, y]` pairs -- exactly
    what `key_points.data[0]` was. `key_points.data[0][i][0]` becomes
    `key_points[i][0]`, and the `.item()` calls are dropped because a Python
    float is already what `.item()` returned. The trace stores
    `float(x)` of the same float32 tensor values, so the operands are
    bit-identical and every subsequent operation is float64 in both versions.
    The arithmetic below is otherwise untouched.
    """
    def _calculate_angle(line1, line2):
        # Calculate the slope of two straight lines
        slope1 = math.atan2(line1[3] - line1[1], line1[2] - line1[0])
        slope2 = math.atan2(line2[3] - line2[1], line2[2] - line2[0])

        # Convert radians to angles
        angle1 = math.degrees(slope1)
        angle2 = math.degrees(slope2)

        # Calculate angle difference
        angle_diff = abs(angle1 - angle2)

        # Ensure the angle is between 0 and 180 degrees
        if angle_diff > 180:
            angle_diff = 360 - angle_diff

        return angle_diff

    # NOTE: no visibility filtering happens here. A keypoint the pose model did
    #       not see is emitted as the (0.0, 0.0) sentinel, `math.atan2(0, 0)`
    #       returns 0.0 rather than raising, and the resulting garbage angle is
    #       averaged in below with full weight. (bug #16)
    left_points = [[key_points[i][0], key_points[i][1]] for i in left_points_idx]
    right_points = [[key_points[i][0], key_points[i][1]] for i in right_points_idx]
    line1_left = [
        left_points[1][0], left_points[1][1],
        left_points[0][0], left_points[0][1]
    ]
    line2_left = [
        left_points[1][0], left_points[1][1],
        left_points[2][0], left_points[2][1]
    ]
    angle_left = _calculate_angle(line1_left, line2_left)
    line1_right = [
        right_points[1][0], right_points[1][1],
        right_points[0][0], right_points[0][1]
    ]
    line2_right = [
        right_points[1][0], right_points[1][1],
        right_points[2][0], right_points[2][1]
    ]
    angle_right = _calculate_angle(line1_right, line2_right)
    # NOTE: unconditional mean of both sides. The caller's visibility test is an
    #       OR over the two sides (lines 321 / 358), so a person visible only
    #       from one side still contributes a fabricated angle from the other.
    angle = (angle_left + angle_right) / 2
    return angle


# ---------------------------------------------------------------------------
# aiModule.py lines 198-214 -- required by the transcribed range, which reads
# `args.sport`, `args.input` and `args2.sport2`. Transcribed unchanged.
# ---------------------------------------------------------------------------
class Args:
    def __init__(self):
        # Set default values
        self.model = 'yolov8s-pose.pt'
        self.sport2 = 'armsUp'
        self.input = "0"
        self.save_dir = None
        self.show = True


class Args2:
    def __init__(self):
        # Set default values
        self.model = 'yolov8s-pose.pt'
        self.sport = 'bending'
        self.input = "0"
        self.save_dir = None
        self.show = True


def replay(frames: Iterable[dict]) -> list[dict]:
    """Return the prediction_data dicts the original code would have sent.

    `frames` yields the trace records described in
    `tests/data/baseline/PROVENANCE.md`. The returned list is in emission order.
    """
    # DEVIATION: materialised so the pre-loop clock initialisation below has a
    # timestamp to anchor on (the original called the real clock before the
    # capture loop started). Consumes the iterable once; no behavioural effect.
    frames = list(frames)

    # SUBSTITUTION 1: the Kafka producer is replaced by this list.
    emitted: list[dict] = []

    # aiModule.py:227,230 -- note the deliberate crossover in the original:
    # `args` is Args2 (sport='bending'), `args2` is Args (sport2='armsUp').
    args = Args2()
    args2 = Args()

    # aiModule.py:222-223
    # NOTE: `bulk_insert_interval` is never read anywhere in the file, and
    #       `data_batch` is emptied immediately after every append (lines 356,
    #       395, 454, 486, 511). The batching machinery is entirely vestigial:
    #       nothing is ever bulk-sent.
    bulk_insert_interval = 60  # noqa: F841  (dead in the original too)
    data_batch = []

    # aiModule.py:253-279 -- state that lives across frames. Required by the
    # transcribed range; transcribed unchanged.
    # NOTE: fixed-size length-10 arrays indexed by detection order. Five or more
    #       people is fine, ten or more raises IndexError. (bug #3)
    # NOTE: nothing associates a slot with a human. YOLO's detection order is
    #       not stable frame to frame, so slot 0's `reaching_last`/`state_keep`
    #       history can belong to a different person on the next frame.
    angle = [0] * 10
    angle2 = [0] * 10
    angle3 = [0] * 10  # noqa: F841  (never read in the original either)
    reaching = [False] * 10
    reaching_last = [False] * 10
    state_keep = [False] * 10
    counter = 0
    # NOTE: the "2" family is initialised with ints while the first family uses
    #       bools. Works only by truthiness; the asymmetry is not intentional.
    reaching2 = [0] * 10
    reaching_last2 = [0] * 10
    state_keep2 = [0] * 10
    counter2 = 0
    x1, y1, x2, y2 = 0, 0, 0, 0
    name = ""
    controlHelmet = False
    controlJacket = False
    # NOTE: these four accumulate for the entire process lifetime and are never
    #       reset after an event is emitted, so `confidencePercentage` on the
    #       Nth NO_HELMET / NO_JACKET is the mean over every detection ever seen,
    #       not over that violation window.
    sumHelmet = 0
    numHelmet = 0
    sumJacket = 0
    numJacket = 0

    # SUBSTITUTION 2/3, applied to the pre-loop clock reads (lines 273/274/279).
    # There is no "current frame" yet, so the first frame's timestamp stands in
    # for the wall clock at process start -- the closest analogue available.
    # `current_time_helmet` / `current_time_jacket` are dead stores (both are
    # overwritten at lines 462/490 before any read), so only `reference_time`
    # can matter, and only by being 3 minutes in the past, which it is either way.
    _start_s = (frames[0]["timestamp_ms"] / 1000.0) if frames else 0.0
    current_time_helmet = _start_s   # time.time()
    current_time_jacket = _start_s   # time.time()
    last_insert_time_helmet = 0
    last_insert_time_jacket = 0
    checkLastSendJacket = False
    checkLastSendHelmet = False
    reference_time = datetime.fromtimestamp(_start_s) - timedelta(minutes=3)

    # NOTE: `numberOfPerson` is deliberately NOT initialised here. In the
    #       original it is a bare local of main(), first assigned at line 315.
    #       Reading it at line 461 before then would be an UnboundLocalError --
    #       unreachable, because line 310's `continue` guarantees line 315 runs
    #       on every frame that can reach line 461. Preserved exactly.

    for frame in frames:
        # SUBSTITUTION 2: every `time.time()` in the transcribed range reads this.
        _now = frame["timestamp_ms"] / 1000.0

        # DEVIATION: `results = model(frame, conf=0.8)` and
        # `results2 = model2.predict(frame, show=False, conf=0.6)` are replaced
        # by the recorded model outputs. `capture_trace.py` invoked the same two
        # models with the same two confidence thresholds (see PROVENANCE.md), so
        # this substitutes recorded inference for live inference and nothing else.
        # `results` is a one-element list exactly as ultralytics returns for a
        # single frame; the `node` / `results[0]` distinction below is preserved.
        results = [frame]

        # aiModule.py:295-298
        # DEVIATION: `classes` holds the resolved label string rather than the
        # float class id, because capture_trace.py already applied
        # `ppe.names[int(cls)]` when writing the trace. `names` is therefore an
        # identity map and line 415 reduces to `name = cls`. Same mapping, one
        # step earlier.
        boxes = [o["box"] for o in frame["objects"]]
        classes = [o["label"] for o in frame["objects"]]
        confidences = [o["confidence"] for o in frame["objects"]]

        # aiModule.py:301 -- `if results[0].keypoints.shape[1] == 0: ... continue`
        # DEVIATION: the trace records exactly this predicate as "empty
        # keypoint lists" (capture_trace.py tests `kp is None or
        # kp.data.shape[1] == 0` and writes `[]`), so the test is on emptiness.
        # NOTE: this `continue` skips lines 312-512 wholesale, i.e. the entire
        #       PPE block. A person-free frame therefore cannot close an open
        #       helmet/jacket violation window, and the preview image is never
        #       rewritten. (bugs #9, #15)
        if len(frame["pose"]["keypoints_xy"]) == 0:
            # (display/teardown lines 302-309 omitted: no frame buffer here)
            continue

        # ===================== aiModule.py line 312 =========================
        confidence_scores = []  # noqa: F841  (never read in the original either)
        for node in results:
            # aiModule.py:314 -- `node.keypoints.conf.tolist()`, shape (P, 17).
            checkNodeVisibility = node["pose"]["keypoint_conf"]
            # NOTE: `checkNodeVisibility[0]` is the FIRST PERSON'S row of 17
            #       keypoint confidences, so `len(...)` is 17 -- always, for any
            #       number of people. `numberOfPerson` is a constant 17 and the
            #       `numberOfPerson > 0` guards at lines 461/489 are no-ops.
            #       (bug #2)
            numberOfPerson = len(checkNodeVisibility[0])
            # aiModule.py:316 -- assigned, never read.
            data = results[0]["pose"]["keypoints_xy"]  # noqa: F841
            personIndex = 0
            # NOTE: the names are inverted. In COCO ordering 11/13/15 are the
            #       LEFT hip/knee/ankle and 12/14/16 the RIGHT ones.
            left = [12, 14, 16]
            right = [11, 13, 15]
            for row in checkNodeVisibility:
                # aiModule.py:321 -- written without parentheses. `and` binds
                # tighter than `or`, so this is (5 and 11 and 13) or
                # (12 and 6 and 14). Transcribed exactly as written.
                if row[5] > 0.6 and row[11] > 0.6 and row[13] > 0.6 or row[12] > 0.6 and row[6] > 0.6 and row[14] > 0.6:
                    # NOTE: this "is the person upright" gate uses ankles (15/16)
                    #       whose visibility the condition above never checked --
                    #       so it routinely feeds (0,0) sentinels to
                    #       calculate_angle.
                    # DEVIATION: `results[0].keypoints[personIndex]` (an
                    # ultralytics Keypoints slice for one person) becomes that
                    # person's list of [x, y] pairs, which is what
                    # `.data[0]` yielded inside calculate_angle.
                    if calculate_angle(results[0]["pose"]["keypoints_xy"][personIndex], left, right) > 160:
                        # Get hyperparameters
                        # NOTE: args.sport is 'bending'. FRONT_BEND is computed
                        #       from the 'bending' config; 'frontbending' is dead.
                        left_points_idx = sport_list[args.sport]['left_points_idx']
                        right_points_idx = sport_list[args.sport]['right_points_idx']
                        # Calculate angle
                        angle[personIndex] = calculate_angle(results[0]["pose"]["keypoints_xy"][personIndex], left_points_idx, right_points_idx)
                        # Determine whether to complete once
                        if angle[personIndex] < sport_list[args.sport]['maintaining']:
                            reaching[personIndex] = True
                        if angle[personIndex] > sport_list[args.sport]['relaxing']:
                            reaching[personIndex] = False
                        if reaching[personIndex] != reaching_last[personIndex]:
                            reaching_last[personIndex] = reaching[personIndex]
                            if reaching[personIndex]:
                                state_keep[personIndex] = True
                            if not reaching[personIndex] and state_keep[personIndex]:
                                # NOTE: `counter` is shared across all people.
                                counter += 1
                                state_keep[personIndex] = False
                                prediction_data = {
                                        # NOTE: `int(_now * 1000)` reproduces
                                        # `int(time.time() * 1000)` under
                                        # substitution 2; the ms -> s -> ms round
                                        # trip is the substitution's own float
                                        # artifact and is deterministic.
                                        "startTime": int(_now * 1000),
                                        "eventType": 'FRONT_BEND',
                                        # NOTE: row[11] is the LEFT HIP KEYPOINT
                                        #       VISIBILITY, not the detection
                                        #       confidence. (bug #5/#7)
                                        "confidencePercentage": row[11],
                                        "cameraName": args.input
                                        # NOTE: no "isProcessed" key here, unlike
                                        #       FALL/NO_HELMET/NO_JACKET below.
                                        }
                                data_batch.append(prediction_data)

                                message = json.dumps(prediction_data).encode('utf-8')

                                key = str(_now).encode('utf-8')
                                # SUBSTITUTION 1:
                                #   producer.send('rawEvents', key=key, value=message)
                                #   producer.flush()
                                emitted.append(prediction_data)

                                # Reset variables for the next interval
                                data_batch = []

                # aiModule.py:358 -- unparenthesised again; (11 and 5 and 7) or
                # (12 and 6 and 8).
                if row[11] > 0.6 and row[5] > 0.6 and row[7] > 0.6 or row[12] > 0.6 and row[6] > 0.6 and row[8] > 0.6:
                    # Get hyperparameters
                    left_points_idx2 = sport_list[args2.sport2]['left_points_idx']
                    right_points_idx2 = sport_list[args2.sport2]['right_points_idx']
                    # Second
                    # Calculate angle
                    angle2[personIndex] = calculate_angle(results[0]["pose"]["keypoints_xy"][personIndex], left_points_idx2, right_points_idx2)

                    # Determine whether to complete once
                    if angle2[personIndex] < sport_list[args2.sport2]['maintaining']:
                        reaching2[personIndex] = True
                    if angle2[personIndex] > sport_list[args2.sport2]['relaxing']:
                        reaching2[personIndex] = False

                    if reaching2[personIndex] != reaching_last2[personIndex]:
                        reaching_last2[personIndex] = reaching2[personIndex]
                        if reaching2[personIndex]:
                            state_keep2[personIndex] = True
                        if not reaching2[personIndex] and state_keep2[personIndex]:
                            counter2 += 1
                            state_keep2[personIndex] = False
                            prediction_data = {
                                        "startTime": int(_now * 1000),
                                        "eventType": 'ARMS_UP',
                                        # NOTE: row[7] is the LEFT ELBOW KEYPOINT
                                        #       VISIBILITY, not the detection
                                        #       confidence. (bug #5/#7)
                                        "confidencePercentage": row[7],
                                        "cameraName": args.input
                                        }
                            data_batch.append(prediction_data)

                            message = json.dumps(prediction_data).encode('utf-8')
                            key = str(_now).encode('utf-8')

                            # SUBSTITUTION 1:
                            #   producer.send('rawEvents', key=key, value=message)
                            #   producer.flush()
                            emitted.append(prediction_data)

                            # Reset variables for the next interval
                            data_batch = []
                # aiModule.py:396-398 -- increment then wrap at numberOfPerson-1.
                # NOTE: since numberOfPerson is the constant 17 (bug #2), the wrap
                #       only fires for an 18th person, which the length-10 state
                #       arrays would already have crashed on. Dead in practice,
                #       but transcribed because it is what the original does.
                personIndex = personIndex + 1
                if personIndex > numberOfPerson - 1:
                    personIndex = 0

        # aiModule.py:400-406 -- `annotated_frame = plot(results[0], ...)`.
        # Omitted: pure rendering, no frame buffer here, no effect on events.

        controlHelmet = True
        # NOTE: THE HEADLINE BUG (#1). `controlJacket` is set False at the top of
        #       every frame and is never assigned True anywhere in the file --
        #       line 428 sets it False *again* on detection. The NO_JACKET block
        #       at line 489 is therefore unreachable and no NO_JACKET event has
        #       ever been published, on any footage.
        controlJacket = False
        # Iterate through the results
        for box, cls, conf in zip(boxes, classes, confidences):
            x1, y1, x2, y2 = box
            confidence = conf  # noqa: F841  (assigned, never read)
            detected_class = cls  # noqa: F841  (assigned, never read)
            # DEVIATION: `name = names[int(cls)]`; the trace pre-resolved it.
            name = cls
            if name == 'no-helmet':
                checkLastSendHelmet = True
                controlHelmet = False
                sumHelmet = sumHelmet + conf
                numHelmet = numHelmet + 1
                if last_insert_time_helmet == 0:
                    last_insert_time_helmet = _now  # time.time()
                current_time_helmet = _now  # time.time()  -- dead store, line 462 overwrites

            if name == 'no-jacket':
                checkLastSendJacket = True
                # NOTE: assigning False here is a no-op; it is already False from
                #       line 409. This is almost certainly where `True` was meant.
                controlJacket = False
                sumJacket = sumJacket + conf
                numJacket = numJacket + 1
                if last_insert_time_jacket == 0:
                    last_insert_time_jacket = _now  # time.time()
                # NOTE: no `current_time_jacket = ...` here, unlike the helmet
                #       branch above. Asymmetric with lines 421-423.

            if name == 'fall':
                # SUBSTITUTION 3: datetime.now()
                current_datetime = datetime.fromtimestamp(_now)
                if current_datetime > reference_time:
                    reference_time = current_datetime + timedelta(minutes=3)
                    prediction_data = {
                        "startTime": int(_now * 1000),
                        "eventType": 'FALL',
                        # NOTE: FALL is the only event that reports the real
                        #       detection confidence.
                        "confidencePercentage": conf,
                        "cameraName": args.input,
                        # NOTE: the string "false", not the boolean false.
                        "isProcessed": "false"
                    }

                    data_batch.append(prediction_data)
                    message = json.dumps(prediction_data).encode('utf-8')

                    key = str(_now).encode('utf-8')
                    # SUBSTITUTION 1:
                    #   producer.send('rawEvents', key=key, value=message)
                    #   producer.flush()
                    emitted.append(prediction_data)

                    # Reset variables for the next interval
                    data_batch = []
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            # aiModule.py:456-458 -- cv2.rectangle / cv2.putText on the annotated
            # frame. Omitted: pure rendering, no effect on events.

        # NOTE: `numberOfPerson > 0` is the constant 17 > 0 (bug #2).
        if checkLastSendHelmet and controlHelmet and numberOfPerson > 0:
            current_time_helmet = _now  # time.time()
            elapsed_time_since_last_insert = current_time_helmet - last_insert_time_helmet
            start_time = last_insert_time_helmet
            end_time = current_time_helmet  # noqa: F841  (assigned, never read)
            prediction_data = {
                # NOTE: seconds, truncated toward zero -- while `startTime` next
                #       to it is milliseconds. A 2.9 s violation reports 2.
                #       (bug #10)
                "timePeriod": int(elapsed_time_since_last_insert),
                "startTime": int(start_time * 1000),
                "eventType": 'NO_HELMET',
                # NOTE: lifetime cumulative mean; sumHelmet/numHelmet are never
                #       reset below.
                "confidencePercentage": sumHelmet / numHelmet,
                "cameraName": args.input,
                "isProcessed": "false"
            }

            data_batch.append(prediction_data)
            last_insert_time_helmet = 0

            message = json.dumps(prediction_data).encode('utf-8')
            key = str(_now).encode('utf-8')
            # SUBSTITUTION 1:
            #   producer.send('rawEvents', key=key, value=message)
            #   producer.flush()
            emitted.append(prediction_data)

            # Reset variables for the next interval
            data_batch = []
            checkLastSendHelmet = False

        # NOTE: UNREACHABLE. `controlJacket` is False on every frame (see line
        #       409 above). Everything below this line is dead code, including
        #       the `last_insert_time_jacket = 0` and `checkLastSendJacket =
        #       False` resets -- so once a no-jacket is seen, both stay latched
        #       for the rest of the process. (bug #1)
        if checkLastSendJacket and controlJacket and numberOfPerson > 0:
            current_time_jacket = _now  # time.time()
            elapsed_time_since_last_insert = current_time_jacket - last_insert_time_jacket
            prediction_data = {
                "timePeriod": int(elapsed_time_since_last_insert),
                "startTime": int(last_insert_time_jacket * 1000),
                "eventType": 'NO_JACKET',
                "confidencePercentage": sumJacket / numJacket,
                "cameraName": args.input,
                "isProcessed": "false"
            }

            data_batch.append(prediction_data)
            last_insert_time_jacket = 0

            message = json.dumps(prediction_data).encode('utf-8')
            key = str(_now).encode('utf-8')

            # SUBSTITUTION 1:
            #   producer.send('rawEvents', key=key, value=message)
            #   producer.flush()
            emitted.append(prediction_data)

            data_batch = []
            checkLastSendJacket = False

        # aiModule.py:514-530 -- put_text / imwrite / waitKey. Out of range and
        # pure display; omitted.

    return emitted
