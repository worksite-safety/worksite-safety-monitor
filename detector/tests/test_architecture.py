"""The boundary that keeps this package testable without a 2 GB CV stack.

`pipeline`, the rule modules and the value objects must never import cv2,
ultralytics, kafka or torch. Only `adapters.py`, `annotate.py` and the
`KafkaEventPublisher.connect` classmethod may touch them, and each is exercised
by the separate `requires_ultralytics` tier.

This is an AST check rather than a `sys.modules` inspection on purpose: by the
time this test runs, another test may already have imported a heavy module, so
runtime inspection would give a false pass.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "worksite_detector"

FORBIDDEN = {"cv2", "ultralytics", "kafka", "torch", "numpy"}

# Modules allowed to import the heavy stack. Everything else must stay pure.
EXEMPT = {"adapters.py", "annotate.py", "publisher.py"}


def _imported_roots(source: str) -> set[str]:
    """Top-level package name of every import in the module."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # `from . import x` has module=None and level>0; not a third party.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _pure_modules() -> list[Path]:
    return sorted(p for p in PACKAGE.glob("*.py") if p.name not in EXEMPT)


def test_package_directory_exists() -> None:
    """Guards against this whole file passing vacuously."""
    assert PACKAGE.is_dir(), f"package not found at {PACKAGE}"


@pytest.mark.parametrize("module", _pure_modules(), ids=lambda p: p.name)
def test_pure_module_has_no_heavy_imports(module: Path) -> None:
    offending = _imported_roots(module.read_text(encoding="utf-8")) & FORBIDDEN
    assert not offending, (
        f"{module.name} imports {sorted(offending)}. "
        f"Only {sorted(EXEMPT)} may touch the CV/Kafka stack — move the dependency "
        f"behind one of those seams so the unit suite keeps running without torch."
    )


def test_publisher_defers_kafka_import() -> None:
    """`publisher.py` is exempt from the module list, but a module-level kafka
    import would still crash `import worksite_detector.publisher` on a machine
    with no broker library. Bug #12 was exactly this. The import must live
    inside a function."""
    path = PACKAGE / "publisher.py"
    if not path.exists():
        pytest.skip("publisher.py not written yet")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:  # module level only, not ast.walk
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module.split(".")[0]] if node.module else []
        else:
            continue
        assert "kafka" not in names, (
            "publisher.py imports kafka at module level; it must be imported inside "
            "the function that needs it, or `import worksite_detector.publisher` "
            "fails wherever kafka-python is absent (bug #12)."
        )
