# -*- coding: utf-8 -*-
"""
Guard against Python 3.9 import crashes.

macOS ships Python 3.9, where ``X | None`` in an annotation raises TypeError at
import unless the module has ``from __future__ import annotations``. Our CI
runs a newer Python, so this static check stops the bug coming back. FastAPI
and pydantic evaluate hints at runtime, so the routers must not use ``|`` at
all (the future import does not protect them) — use ``Optional[...]``.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_DIRS = ("utils", "api")
RUNTIME_EVALUATED_DIRS = ("api/routers",)


def _annotations(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            yield node.returns
        elif isinstance(node, ast.AnnAssign):
            yield node.annotation


def _uses_union(annotation: ast.AST) -> bool:
    return any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(annotation))


def _has_future_annotations(tree: ast.Module) -> bool:
    return any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
               and any(a.name == "annotations" for a in n.names) for n in tree.body)


def problems(source: str, runtime_evaluated: bool = False) -> list[str]:
    """Human-readable list of Python 3.9 incompatibilities in ``source``."""
    tree = ast.parse(source)
    unions = [a for a in _annotations(tree) if _uses_union(a)]
    if not unions:
        return []
    if runtime_evaluated:
        return [f"line {a.lineno}: `X | Y` annotation is evaluated at runtime by FastAPI/pydantic; use Optional/Union"
                for a in unions]
    if not _has_future_annotations(tree):
        return [f"line {a.lineno}: `X | Y` annotation needs `from __future__ import annotations`" for a in unions]
    return []


class CheckerSelfTests(unittest.TestCase):
    def test_flags_missing_future_import(self):
        self.assertTrue(problems("def f(x: str | None): pass\n"))

    def test_accepts_future_import(self):
        self.assertEqual(problems("from __future__ import annotations\ndef f(x: str | None): pass\n"), [])

    def test_flags_class_and_return_annotations(self):
        self.assertTrue(problems("class A:\n    y: int | None = None\n"))
        self.assertTrue(problems("def f() -> int | None: pass\n"))

    def test_runtime_evaluated_modules_reject_even_with_future_import(self):
        src = "from __future__ import annotations\ndef f(x: str | None = None): pass\n"
        self.assertTrue(problems(src, runtime_evaluated=True))
        self.assertEqual(problems("from typing import Optional\ndef f(x: Optional[str] = None): pass\n", runtime_evaluated=True), [])

    def test_plain_bitor_expressions_are_not_flagged(self):
        self.assertEqual(problems("x = 1 | 2\ndef f(a: int): return a | 1\n"), [])


class RepositoryTests(unittest.TestCase):
    def test_no_python39_import_crashes_in_source(self):
        bad = []
        for d in SCAN_DIRS:
            for path in sorted((REPO / d).rglob("*.py")):
                rel = path.relative_to(REPO).as_posix()
                runtime = any(rel.startswith(p + "/") for p in RUNTIME_EVALUATED_DIRS)
                for msg in problems(path.read_text(encoding="utf-8"), runtime_evaluated=runtime):
                    bad.append(f"{rel}: {msg}")
        self.assertEqual(bad, [], "Python 3.9 incompatibilities:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
