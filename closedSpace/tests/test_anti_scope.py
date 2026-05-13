"""ISC-30 + ISC-35 probes: closedSpace stays out of CV/OCR/GPS land.

ISC-30 (no `GPSProvider`) and ISC-35 (no inference / OCR / CV-recognition
library) are static-import checks. We enforce them with the same
AST-walking pattern as the engine anti-bleed test — substring matches
in docstrings are deliberately ignored so the ISA / CLAUDE.md can
discuss the forbidden libraries without tripping the gate.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

CLOSED_SPACE_ROOT = Path(__file__).resolve().parents[1]

#: Root module names that closedSpace MUST NOT import. The CV/OCR set
#: comes straight from §10 of the ISA "Out of Scope" list: onboard SKU
#: recognition is downstream, not on the drone.
_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "cv2",
        "easyocr",
        "paddleocr",
        "ultralytics",
        "tesseract",
        "pytesseract",
        "torch",
        "torchvision",
        "tensorflow",
        "keras",
    }
)

#: Symbols that, if imported by name from any module, indicate a leak.
#: GPSProvider stays here as a regression guard even though the
#: anti-bleed test in engine/ also catches it — defense in depth.
_FORBIDDEN_SYMBOLS = frozenset({"GPSProvider"})


def _python_sources() -> list[Path]:
    return [p for p in CLOSED_SPACE_ROOT.rglob("*.py") if "tests" not in p.parts]


def _scan(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _FORBIDDEN_IMPORT_ROOTS:
                    hits.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if root in _FORBIDDEN_IMPORT_ROOTS:
                hits.append(f"from {module} import …")
            for alias in node.names:
                if alias.name in _FORBIDDEN_SYMBOLS:
                    hits.append(f"from {module or '?'} import {alias.name}")
    return hits


@pytest.mark.parametrize("source", _python_sources(), ids=lambda p: str(p))
def test_no_forbidden_imports(source: Path) -> None:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    hits = _scan(tree)
    assert not hits, (
        f"{source.relative_to(CLOSED_SPACE_ROOT.parent)} contains forbidden imports: "
        f"{hits!r}. ISC-30 forbids GPSProvider; ISC-35 forbids "
        f"inference/OCR/CV-recognition libraries (see Out-of-Scope §)."
    )
