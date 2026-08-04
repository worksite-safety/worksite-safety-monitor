"""Freeze the legacy behaviour: replay the trace through the oracle, write events.

    ../.venv/Scripts/python.exe tests/data/baseline/build_baseline.py

Reads `trace.jsonl.gz`, runs it through `legacy_oracle.replay`, and writes
`baseline_events.jsonl` -- one JSON object per line, in emission order. That
file is the contract the rewritten detector is diffed against.

Deterministic: no clock, no network, no models. Re-running it must produce a
byte-identical file (enforced by tests/test_baseline_oracle.py).
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from legacy_oracle import replay  # noqa: E402

TRACE = HERE / "trace.jsonl.gz"
OUT = HERE / "baseline_events.jsonl"


def load_trace(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(argv: list[str] | None = None) -> int:
    if not TRACE.exists():
        print(f"trace not found: {TRACE}", file=sys.stderr)
        return 1

    frames = load_trace(TRACE)
    events = replay(frames)

    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for event in events:
            fh.write(json.dumps(event, sort_keys=False) + "\n")

    counts = Counter(e["eventType"] for e in events)

    print(f"frames replayed : {len(frames)}")
    print(f"events emitted  : {len(events)}")
    for event_type in sorted(counts):
        print(f"  {event_type:<12} {counts[event_type]}")
    for event_type in ("FALL", "NO_HELMET", "NO_JACKET", "ARMS_UP", "FRONT_BEND"):
        if event_type not in counts:
            print(f"  {event_type:<12} 0")
    print(f"written         : {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
