"""Resolve Node, Godot and shell dynamic execution targets."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Iterable, Iterator, List

from scripts.governance.boundaries.effective_dependencies.targets import (
    normalize_module_target,
    targets_from_tokens,
)

NODE_PROCESS_CALLS = (
    "execFileSync",
    "execFile",
    "execSync",
    "spawnSync",
    "spawn",
    "fork",
    "exec",
)
GODOT_PROCESS_CALLS = ("execute_with_pipe", "create_process", "execute")
NODE_DYNAMIC_IMPORT_PATTERN = re.compile(
    r"\b(?P<call>import|require)\s*\(\s*['\"](?P<target>[^'\"]+)['\"]"
)
QUOTED_VALUE_PATTERN = re.compile(r"['\"]([^'\"]+)['\"]")


def _process_calls(
    source: str, call_names: Iterable[str]
) -> Iterator[tuple[str, int, str]]:
    call_pattern = re.compile(
        r"\b(" + "|".join(re.escape(name) for name in call_names) + r")\s*\("
    )
    for match in call_pattern.finditer(source):
        depth = 1
        quote = ""
        escaped = False
        cursor = match.end()
        while cursor < len(source) and depth:
            character = source[cursor]
            if quote:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = ""
            elif character in {"'", '"', "`"}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            cursor += 1
        if depth == 0:
            yield match.group(1), match.start(), source[match.end() : cursor - 1]


def _quoted_targets(arguments: str) -> List[str]:
    tokens: List[str] = []
    for value in QUOTED_VALUE_PATTERN.findall(arguments):
        try:
            tokens.extend(shlex.split(value))
        except ValueError:
            tokens.append(value)
    return sorted(targets_from_tokens(tokens))


def node_dependencies(path: Path) -> Iterator[tuple[int, str, str]]:
    """Yield dynamic imports and child-process targets from Node source."""
    source = path.read_text(encoding="utf-8")
    for match in NODE_DYNAMIC_IMPORT_PATTERN.finditer(source):
        target = normalize_module_target(match.group("target"))
        if target:
            yield source.count("\n", 0, match.start()) + 1, match.group("call"), target
    for call_name, start, arguments in _process_calls(source, NODE_PROCESS_CALLS):
        for target in _quoted_targets(arguments):
            yield source.count("\n", 0, start) + 1, call_name, target


def godot_dependencies(path: Path) -> Iterator[tuple[int, str, str]]:
    """Yield repository targets from Godot process calls."""
    source = path.read_text(encoding="utf-8")
    for call_name, start, arguments in _process_calls(source, GODOT_PROCESS_CALLS):
        for target in _quoted_targets(arguments):
            yield source.count("\n", 0, start) + 1, call_name, target


def shell_dependencies(path: Path) -> Iterator[tuple[int, str, str]]:
    """Yield repository module and script targets from shell source."""
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            continue
        for target in sorted(targets_from_tokens(tokens)):
            yield line_number, "shell", target
