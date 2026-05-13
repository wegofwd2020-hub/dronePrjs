"""ISC-41 probe: every closedSpace source module has a test mirror.

Rule:

* ``closedSpace/X/Y.py`` requires ``closedSpace/tests/X/test_Y.py``.
* ``closedSpace/Y.py`` requires ``closedSpace/tests/test_Y.py``.

Exempt: ``__init__.py`` files, and modules whose only content is
type/constant declarations (no behavior worth a dedicated test). The
exemption list is enumerated explicitly so adding a new pure-data
module is a deliberate one-line change here.
"""
from __future__ import annotations

from pathlib import Path

CLOSED_SPACE_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = CLOSED_SPACE_ROOT / "tests"

#: Source modules deliberately excluded from the file-pair requirement.
#: Pure data and constants don't carry behavior worth a dedicated test;
#: their fields are exercised through whatever consumer imports them.
_EXEMPT_RELATIVE: frozenset[str] = frozenset(
    {
        "constants.py",
        "map/types.py",
        "mission/types.py",
    }
)


def _expected_test_path(source_rel: Path) -> Path:
    """Map ``X/Y.py`` → ``tests/X/test_Y.py`` (or ``tests/test_Y.py`` if flat)."""
    parts = source_rel.parts
    if len(parts) == 1:
        return TESTS_ROOT / f"test_{parts[0]}"
    return TESTS_ROOT.joinpath(*parts[:-1]) / f"test_{parts[-1]}"


def test_every_source_module_has_a_test_mirror() -> None:
    missing: list[tuple[Path, Path]] = []
    for source in CLOSED_SPACE_ROOT.rglob("*.py"):
        if "tests" in source.parts:
            continue
        if source.name == "__init__.py":
            continue
        rel = source.relative_to(CLOSED_SPACE_ROOT)
        if str(rel) in _EXEMPT_RELATIVE:
            continue
        expected = _expected_test_path(rel)
        if not expected.is_file():
            missing.append((rel, expected.relative_to(CLOSED_SPACE_ROOT.parent)))

    assert not missing, (
        "ISC-41 violations — these source modules have no test mirror:\n"
        + "\n".join(f"  {src}  →  expected {dst}" for src, dst in missing)
        + "\nEither add the test file or add the source path to "
        "_EXEMPT_RELATIVE with a justification."
    )
