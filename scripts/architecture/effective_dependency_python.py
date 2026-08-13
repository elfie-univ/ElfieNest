"""Resolve Python dynamic-load and process targets with AST analysis."""

from __future__ import annotations

import ast
import shlex
from pathlib import Path
from typing import Dict, FrozenSet, Iterator, List, Mapping

from scripts.architecture.effective_dependency_targets import (
    normalize_module_target,
    targets_from_tokens,
)

PROCESS_CALLS = frozenset(
    {
        "asyncio.create_subprocess_exec",
        "asyncio.create_subprocess_shell",
        "os.execl",
        "os.execle",
        "os.execlp",
        "os.execlpe",
        "os.execv",
        "os.execve",
        "os.execvp",
        "os.execvpe",
        "os.popen",
        "os.spawnl",
        "os.spawnle",
        "os.spawnlp",
        "os.spawnlpe",
        "os.spawnv",
        "os.spawnve",
        "os.spawnvp",
        "os.spawnvpe",
        "os.system",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.run",
    }
)
DYNAMIC_MODULE_CALLS = frozenset(
    {"__import__", "importlib.import_module", "runpy.run_module"}
)


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _import_aliases(tree: ast.AST) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _assignments(tree: ast.AST) -> Dict[str, ast.AST]:
    values: Dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and value is not None:
                values[target.id] = value
    return values


def _literal_tokens(
    node: ast.AST,
    assignments: Mapping[str, ast.AST],
    *,
    resolving: FrozenSet[str] = frozenset(),
) -> List[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return shlex.split(node.value)
        except ValueError:
            return [node.value]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        tokens: List[str] = []
        for element in node.elts:
            tokens.extend(_literal_tokens(element, assignments, resolving=resolving))
        return tokens
    if (
        isinstance(node, ast.Name)
        and node.id in assignments
        and node.id not in resolving
    ):
        return _literal_tokens(
            assignments[node.id],
            assignments,
            resolving=resolving | frozenset({node.id}),
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return [
            *_literal_tokens(node.left, assignments, resolving=resolving),
            *_literal_tokens(node.right, assignments, resolving=resolving),
        ]
    return []


def _resolved_call_name(node: ast.Call, aliases: Mapping[str, str]) -> str:
    name = _qualified_name(node.func)
    first, separator, rest = name.partition(".")
    resolved = aliases.get(first, first)
    return f"{resolved}.{rest}" if separator else resolved


def python_dependencies(path: Path) -> Iterator[tuple[int, str, str]]:
    """Yield resolvable repository targets from one Python source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _import_aliases(tree)
    assignments = _assignments(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _resolved_call_name(node, aliases)
        if call_name in DYNAMIC_MODULE_CALLS and node.args:
            for token in _literal_tokens(node.args[0], assignments):
                target = normalize_module_target(token)
                if target:
                    yield node.lineno, call_name, target
        if call_name not in PROCESS_CALLS:
            continue
        expressions: List[ast.AST] = []
        if call_name == "asyncio.create_subprocess_exec":
            expressions.extend(node.args)
        elif node.args:
            expressions.append(node.args[0])
        else:
            expressions.extend(
                keyword.value for keyword in node.keywords if keyword.arg == "args"
            )
        tokens: List[str] = []
        for expression in expressions:
            tokens.extend(_literal_tokens(expression, assignments))
        for target in sorted(targets_from_tokens(tokens)):
            yield node.lineno, call_name, target
