"""COCO-17 keypoint indices, by name.

YOLOv8 pose models emit the 17 COCO keypoints in this fixed order, and
`aiModule.py` addresses them as bare integers everywhere -- `row[11] > 0.6`,
`left_points_idx: [5, 11, 13]`, `left = [12, 14, 16]`. Reading that code means
decoding the numbering in your head on every line, which is how the swap
documented below survived. Downstream tests say `LEFT_HIP`; they never say 11.

The order is the COCO person keypoint order, which is normative for every model
in the `yolov8*-pose` family:

    0  nose            1  left_eye       2  right_eye
    3  left_ear        4  right_ear
    5  left_shoulder   6  right_shoulder
    7  left_elbow      8  right_elbow
    9  left_wrist     10  right_wrist
    11 left_hip       12  right_hip
    13 left_knee      14  right_knee
    15 left_ankle     16  right_ankle

"left" and "right" are the *subject's* left and right, not the viewer's.

**Where `aiModule.py` disagrees.** Lines 318-319 read

    left  = [12, 14, 16]
    right = [11, 13, 15]

which is the COCO numbering mirrored: 12/14/16 are the *right* hip, knee and
ankle and 11/13/15 are the *left* ones. The two lists are then passed to
`calculate_angle(..., left_points_idx, right_points_idx)`, which averages the
two sides unconditionally (line 87), so swapping the labels does not change
that call's result -- the defect is in the naming, not the arithmetic, and it
is exactly the kind of thing a named constant makes impossible. Every other
index list in the file (`sport_list`, lines 20-45) uses the correct sides.
"""
from __future__ import annotations

NOSE = 0
LEFT_EYE = 1
RIGHT_EYE = 2
LEFT_EAR = 3
RIGHT_EAR = 4
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_ELBOW = 7
RIGHT_ELBOW = 8
LEFT_WRIST = 9
RIGHT_WRIST = 10
LEFT_HIP = 11
RIGHT_HIP = 12
LEFT_KNEE = 13
RIGHT_KNEE = 14
LEFT_ANKLE = 15
RIGHT_ANKLE = 16

KEYPOINT_COUNT = 17

#: Index -> name, for assertion messages that name the joint that failed.
KEYPOINT_NAMES: tuple[str, ...] = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)

#: The keypoints belonging to each side of the body. `make_person` hides a side
#: by zeroing exactly these entries, which is what YOLO does to a limb it never
#: saw. `NOSE` is on neither list: it is the one midline keypoint and stays
#: visible however the subject is turned.
LEFT_SIDE_INDICES: tuple[int, ...] = (
    LEFT_EYE,
    LEFT_EAR,
    LEFT_SHOULDER,
    LEFT_ELBOW,
    LEFT_WRIST,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_ANKLE,
)
RIGHT_SIDE_INDICES: tuple[int, ...] = (
    RIGHT_EYE,
    RIGHT_EAR,
    RIGHT_SHOULDER,
    RIGHT_ELBOW,
    RIGHT_WRIST,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_ANKLE,
)
MIDLINE_INDICES: tuple[int, ...] = (NOSE,)
