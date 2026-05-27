#!/usr/bin/env python3
"""AST-based checker for suspicious try/except patterns."""

import ast
import sys
from pathlib import Path

BROAD_EXCEPTIONS = {"Exception", "BaseException"}


def _is_broad_exception(node: ast.expr | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name) and node.id in BROAD_EXCEPTIONS:
        return True
    if isinstance(node, ast.Tuple):
        return any(isinstance(elt, ast.Name) and elt.id in BROAD_EXCEPTIONS for elt in node.elts)
    return False


def _has_raise(body: list[ast.stmt]) -> bool:
    return any(isinstance(child, ast.Raise) for stmt in body for child in ast.walk(stmt))


def _returns_constant(body: list[ast.stmt]) -> bool:
    constant_nodes = (ast.Constant, ast.List, ast.Dict, ast.Tuple)
    return any(
        isinstance(child, ast.Return)
        and child.value is not None
        and isinstance(child.value, constant_nodes)
        for stmt in body
        for child in ast.walk(stmt)
    )


def check_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    except SyntaxError as exc:
        return [f"{path}: syntax error: {exc}"]

    issues: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            location = f"{path}:{handler.lineno}:{handler.col_offset}"
            if handler.type is None:
                issues.append(f"{location} bare except catches all exceptions")
                continue
            if _is_broad_exception(handler.type) and not _has_raise(handler.body):
                issues.append(f"{location} broad exception catch without re-raise")
            if _returns_constant(handler.body):
                issues.append(f"{location} except block returns a constant/default value")
    return issues


def iter_python_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(
                file
                for file in path.rglob("*.py")
                if "__pycache__" not in file.parts and ".venv" not in file.parts
            )
    return files


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]] or [Path("backend")]
    issues: list[str] = []
    for file in iter_python_files(paths):
        issues.extend(check_file(file))

    if not issues:
        print("No suspicious try/except patterns found.")
        return 0

    print(f"Found {len(issues)} suspicious try/except patterns:\n")
    for issue in issues:
        print(f"  {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
