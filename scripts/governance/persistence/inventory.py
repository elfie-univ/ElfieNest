"""Read-only database consumer inventory and boundary checks."""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCANNED_SOURCE_ROOTS = (
    "app",
    "devtools",
    "elfie",
    "infrastructure",
    "nest",
    "scripts",
    "test",
)
GENERATED_DIRECTORY_NAMES = frozenset(
    {".git", ".venv", "__pycache__", "build", "dist", "node_modules"}
)
ALLOWED_SQL_ROOTS = (
    "infrastructure/persistence/",
    "elfie/brain/memory/",
    "app/infrastructure/devices/",
)
DATABASE_CHANGE_ROOTS = ALLOWED_SQL_ROOTS
SQL_REFERENCE_PATTERN = re.compile(
    r"\b(?P<operation>INSERT\s+INTO|UPDATE\s+(?!OF\b|ON\b|SET\b|WHERE\b)|"
    r"DELETE\s+FROM|FROM|JOIN|CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|"
    r"CREATE(?:\s+UNIQUE)?\s+INDEX|CREATE\s+TRIGGER|REFERENCES|ON)\s+"
    r'(?:IF\s+(?:NOT\s+)?EXISTS\s+)?["]?(?P<table>'
    r'[A-Za-z_][A-Za-z0-9_]*)["]?',
    re.IGNORECASE,
)
SQL_STATEMENT_START_PATTERN = re.compile(
    r"\b(?:SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+[A-Za-z_]"
    r"[A-Za-z0-9_]*\s+(?:SET|WHERE)|DELETE\s+FROM|CREATE\s+"
    r"(?:TABLE|(?:UNIQUE\s+)?INDEX|TRIGGER)|ALTER\s+TABLE|DROP\s+TABLE|"
    r"PRAGMA\s+|BEGIN\s+(?:DEFERRED|IMMEDIATE|EXCLUSIVE))\b",
    re.IGNORECASE,
)
SCHEMA_ON_PATTERN = re.compile(
    r"\bCREATE(?:\s+UNIQUE)?\s+(?:INDEX|TRIGGER)\b.*?\bON\s+"
    r'["]?([A-Za-z_][A-Za-z0-9_]*)["]?',
    re.IGNORECASE | re.DOTALL,
)
TRANSIENT_FINAL_STATE_PATTERN = re.compile(
    r"\b(?:admission_state|provisioning|pending|in_progress|processing|draft)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DatabaseReference:
    """One SQL reference found in a Python string literal."""

    path: str
    line: int
    operation: str
    table: str
    snippet: str


@dataclass(frozen=True)
class DatabaseInventory:
    """Read-only result used by the CLI and architecture tests."""

    references: Tuple[DatabaseReference, ...]
    parse_errors: Tuple[str, ...]


def _source_files(project_root: Path) -> Iterable[Path]:
    for relative_root in SCANNED_SOURCE_ROOTS:
        root = project_root / relative_root
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if not GENERATED_DIRECTORY_NAMES.intersection(path.parts):
                yield path


def _normalize_operation(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().upper())


def collect_inventory(project_root: Path = PROJECT_ROOT) -> DatabaseInventory:
    references: List[DatabaseReference] = []
    parse_errors: List[str] = []
    for path in _source_files(project_root):
        relative_path = path.relative_to(project_root).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=relative_path)
        except SyntaxError as error:
            parse_errors.append(f"{relative_path}:{error.lineno}: {error.msg}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if SQL_STATEMENT_START_PATTERN.search(node.value) is None:
                continue
            snippet = " ".join(node.value.strip().split())[:160]
            for match in SQL_REFERENCE_PATTERN.finditer(node.value):
                operation = _normalize_operation(match.group("operation"))
                if operation == "ON":
                    continue
                references.append(
                    DatabaseReference(
                        path=relative_path,
                        line=int(getattr(node, "lineno", 1)),
                        operation=operation,
                        table=match.group("table"),
                        snippet=snippet,
                    )
                )
            for match in SCHEMA_ON_PATTERN.finditer(node.value):
                references.append(
                    DatabaseReference(
                        path=relative_path,
                        line=int(getattr(node, "lineno", 1)),
                        operation="CREATE INDEX/TRIGGER ON",
                        table=match.group(1),
                        snippet=snippet,
                    )
                )
    references.sort(key=lambda item: (item.table, item.path, item.line, item.operation))
    return DatabaseInventory(tuple(references), tuple(sorted(parse_errors)))


def changed_paths(base_sha: str, project_root: Path = PROJECT_ROOT) -> Tuple[str, ...]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACDMRTUXB",
            f"{base_sha}...HEAD",
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line)


def database_change_paths(paths: Iterable[str]) -> Tuple[str, ...]:
    return tuple(
        sorted(
            path
            for path in paths
            if any(path.startswith(root) for root in DATABASE_CHANGE_ROOTS)
            and not path.endswith("/AGENTS.md")
            and Path(path).suffix.lower() in {".py", ".sql"}
        )
    )


def transient_final_state_violations(
    project_root: Path,
) -> Tuple[str, ...]:
    """Reject process state embedded in the final Elfie fact table."""

    schema_path = project_root / "infrastructure/persistence/nest_db/final_schema.py"
    source = schema_path.read_text(encoding="utf-8")
    start = source.find("CREATE TABLE IF NOT EXISTS elfies")
    end = source.find("CREATE TABLE IF NOT EXISTS food_packages", start)
    if start < 0 or end < 0:
        return ("final_schema.py does not expose a recognizable elfies table block",)
    block = source[start:end]
    matches = sorted(
        {match.group(0) for match in TRANSIENT_FINAL_STATE_PATTERN.finditer(block)}
    )
    return tuple(
        f"final elfies table contains transient state marker: {marker}"
        for marker in matches
    )


def sql_boundary_violations(inventory: DatabaseInventory) -> Tuple[str, ...]:
    violations = []
    for reference in inventory.references:
        if reference.path.startswith("test/"):
            continue
        if reference.path.startswith("scripts/governance/"):
            continue
        if any(reference.path.startswith(root) for root in ALLOWED_SQL_ROOTS):
            continue
        if not reference.path.startswith(
            ("app/", "devtools/", "elfie/", "nest/", "scripts/")
        ):
            continue
        violations.append(
            f"SQL outside persistence boundary: {reference.path}:{reference.line} "
            f"{reference.operation} {reference.table}"
        )
    return tuple(sorted(set(violations)))


def render_inventory(inventory: DatabaseInventory) -> str:
    grouped: dict[str, list[DatabaseReference]] = {}
    for reference in inventory.references:
        grouped.setdefault(reference.table, []).append(reference)
    lines = ["Database consumer inventory (read-only):"]
    for table in sorted(grouped):
        lines.append(f"[{table}]")
        seen: set[tuple[str, int, str]] = set()
        for reference in grouped[table]:
            key = (reference.path, reference.line, reference.operation)
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"- {reference.path}:{reference.line} "
                f"{reference.operation} {reference.table}"
            )
    if inventory.parse_errors:
        lines.append("Parse errors:")
        lines.extend(f"- {error}" for error in inventory.parse_errors)
    return "\n".join(lines)


def check(
    project_root: Path,
    base_sha: str | None = None,
    inventory: DatabaseInventory | None = None,
) -> Tuple[str, ...]:
    inventory = inventory or collect_inventory(project_root)
    failures = list(inventory.parse_errors)
    failures.extend(transient_final_state_violations(project_root))
    failures.extend(sql_boundary_violations(inventory))
    if base_sha is not None:
        db_paths = database_change_paths(changed_paths(base_sha, project_root))
        if db_paths:
            print(
                "Database files changed; full consumer inventory is required for review:"
            )
            print("\n".join(f"- {path}" for path in db_paths))
            print(render_inventory(inventory))
    return tuple(sorted(set(failures)))
