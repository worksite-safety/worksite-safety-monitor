"""Stage A of the baseline: record what the models actually saw.

Runs the two YOLO models over a clip and writes one JSON object per frame
holding their raw outputs -- not events. The schema is deliberately identical to
the boundary DTOs `pipeline.py` will consume, so the same trace can be replayed
through both the transcribed legacy logic (Stage B) and the rewritten pipeline
(Stage C) and the two compared.

Model invocations mirror the original aiModule.py exactly:
    pose: YOLO("yolov8s-pose.pt")(frame, conf=0.8)     (line 291)
    ppe:  YOLO("best.pt").predict(frame, conf=0.6)     (line 293)

Requires the `cv` extra. Not part of the unit suite.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--pose-model", required=True)
    p.add_argument("--ppe-model", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--stride", type=int, default=1, help="process every Nth frame")
    p.add_argument("--limit", type=int, default=0, help="stop after N processed frames")
    p.add_argument("--pose-conf", type=float, default=0.8)
    p.add_argument("--ppe-conf", type=float, default=0.6)
    args = p.parse_args(argv)

    import cv2
    from ultralytics import YOLO

    pose_model = YOLO(args.pose_model)
    ppe_model = YOLO(args.ppe_model)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"cannot open {args.video}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    processed = 0
    read_index = 0
    started = time.perf_counter()
    stats = {"frames": 0, "frames_with_person": 0, "person_detections": 0, "labels": {}}

    with gzip.open(out_path, "wt", encoding="utf-8") as fh:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if read_index % args.stride != 0:
                read_index += 1
                continue
            timestamp_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))

            pose = pose_model(frame, conf=args.pose_conf, verbose=False)[0]
            ppe = ppe_model.predict(frame, show=False, conf=args.ppe_conf, verbose=False)[0]

            kp = pose.keypoints
            if kp is None or kp.data.shape[1] == 0:
                keypoints_xy: list = []
                keypoint_conf: list = []
            else:
                keypoints_xy = [[[float(x), float(y)] for x, y in person[:, :2].tolist()]
                                for person in kp.data]
                keypoint_conf = ([[float(c) for c in person] for person in kp.conf.tolist()]
                                 if kp.conf is not None else
                                 [[float(person[i][2]) for i in range(len(person))]
                                  for person in kp.data.tolist()])
            box_conf = ([float(c) for c in pose.boxes.conf.tolist()]
                        if pose.boxes is not None else [])

            objects = []
            for box, cls, conf in zip(ppe.boxes.xyxy.tolist(),
                                      ppe.boxes.cls.tolist(),
                                      ppe.boxes.conf.tolist(), strict=True):
                label = ppe.names[int(cls)]
                objects.append({
                    "label": label,
                    "confidence": float(conf),
                    "box": [int(v) for v in box],
                })
                stats["labels"][label] = stats["labels"].get(label, 0) + 1

            fh.write(json.dumps({
                "index": processed,
                "source_frame": read_index,
                "timestamp_ms": timestamp_ms,
                "pose": {
                    "keypoints_xy": keypoints_xy,
                    "keypoint_conf": keypoint_conf,
                    "box_conf": box_conf,
                },
                "objects": objects,
            }) + "\n")

            stats["frames"] += 1
            if keypoints_xy:
                stats["frames_with_person"] += 1
                stats["person_detections"] += len(keypoints_xy)

            processed += 1
            read_index += 1
            if processed % 25 == 0:
                rate = processed / (time.perf_counter() - started)
                print(f"  {processed} frames  ({rate:.2f} fps)", flush=True)
            if args.limit and processed >= args.limit:
                break

    cap.release()
    elapsed = time.perf_counter() - started
    print(json.dumps({"elapsed_s": round(elapsed, 1),
                      "fps": round(processed / elapsed, 2) if elapsed else 0,
                      "out_bytes": out_path.stat().st_size,
                      **stats}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
