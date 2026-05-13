"""ISC-36 probe: no domain-specific code leaks into ``engine/``.

The engine is the cross-domain contract; it must not depend on
``closedSpace`` or ``openSpace``. We enforce this via static analysis
of the AST: every ``import`` or ``from … import`` whose root module is
a domain package fails the test. Substring matches in docstrings are
deliberately ignored — saying "closedSpace must use SLAMProvider" in
prose doesn't create a dependency.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]

#: Root module names that the engine MUST NOT import.
_FORBIDDEN_ROOTS = frozenset({"closedSpace", "openSpace"})


def _python_sources() -> list[Path]:
    return [p for p in ENGINE_ROOT.rglob("*.py") if "tests" not in p.parts]


def _forbidden_imports(tree: ast.AST) -> list[str]:
    """Return every imported module whose root is a forbidden domain."""
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _FORBIDDEN_ROOTS:
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in _FORBIDDEN_ROOTS:
                hits.append(node.module)
    return hits


@pytest.mark.parametrize("source", _python_sources(), ids=lambda p: str(p))
def test_no_domain_imports(source: Path) -> None:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    hits = _forbidden_imports(tree)
    assert not hits, (
        f"{source.relative_to(ENGINE_ROOT.parent)} imports {hits!r} — "
        "engine must not depend on closedSpace/openSpace"
    )
