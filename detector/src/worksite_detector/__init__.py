"""Worksite safety detector.

Reads frames from a camera or video file, runs a pose model and a PPE/fall
model over each one, and publishes safety events to Kafka.

The package is deliberately split so that everything carrying a decision --
`events`, `geometry`, `config`, `pose_rules`, `ppe_rules`, `draw_plan`,
`pipeline` -- is pure Python with no computer-vision dependency. Only
`adapters`, `annotate` and one classmethod in `publisher` touch cv2,
ultralytics or kafka. `tests/test_architecture.py` enforces that boundary.
"""

__version__ = "1.0.0"
