"""The baseline is only worth freezing if it is reproducible.

`legacy_oracle.replay` is a transcription of code that read the wall clock
(`time.time()`, `datetime.now()`) on every frame. If any of those reads survived
the transcription, or if event ordering depended on set/dict iteration, the
frozen `baseline_events.jsonl` would drift and every differential comparison
against it would be noise. This test pins that down before the file is trusted.
"""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

BASELINE_DIR = Path(__file__).resolve().parent / "data" / "baseline"
TRACE = BASELINE_DIR / "trace.jsonl.gz"
ORACLE = BASELINE_DIR / "legacy_oracle.py"


def _load_oracle():
    """Import legacy_oracle.py by path -- tests/data/baseline is a data
    directory, not an importable package, and should stay that way."""
    spec = importlib.util.spec_from_file_location("legacy_oracle", ORACLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_trace() -> list[dict]:
    with gzip.open(TRACE, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _serialise(events: list[dict]) -> bytes:
    return b"".join(json.dumps(e).encode("utf-8") + b"\n" for e in events)


def test_oracle_replay_is_deterministic() -> None:
    if not TRACE.exists():
        pytest.skip(f"baseline trace not present: {TRACE}")

    oracle = _load_oracle()

    first = _serialise(oracle.replay(_load_trace()))
    second = _serialise(oracle.replay(_load_trace()))

    assert first == second, (
        "legacy_oracle.replay is not deterministic: two replays of the same "
        "trace differ. Something still reads the wall clock or depends on "
        "unordered iteration, so baseline_events.jsonl cannot be frozen."
    )
    assert first, "replay produced no events at all -- the trace or the oracle is wrong"
