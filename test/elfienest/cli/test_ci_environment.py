from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_ci_actions_are_pinned_to_full_commit_shas() -> None:
    # Given
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    # When
    action_references = re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, re.MULTILINE)

    # Then
    assert action_references
    assert all(
        re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference)
        for reference in action_references
    )


def test_ci_uses_read_only_repository_permissions() -> None:
    # Given
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    # When
    has_read_only_permissions = bool(
        re.search(r"^permissions:\s*\n\s+contents:\s+read\s*$", workflow, re.MULTILINE)
    )

    # Then
    assert has_read_only_permissions


def test_documentation_does_not_recommend_privileged_installation() -> None:
    # Given
    guide = (PROJECT_ROOT / "CLI_GUIDE.md").read_text(encoding="utf-8")

    # When
    recommends_sudo_install = bool(re.search(r"sudo\s+\./install\.sh", guide))

    # Then
    assert not recommends_sudo_install


def test_python_guides_use_the_locked_environment_contract() -> None:
    # Given
    python_guide = (PROJECT_ROOT / "docs" / "Python代码规范.md").read_text(
        encoding="utf-8"
    )
    lab_design = (PROJECT_ROOT / "ELFIE_LAB_DESIGN.md").read_text(encoding="utf-8")
    agents_guide = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    # When
    stale_contracts = (
        'requires-python = ">=3.9,<3.10"',
        "actions/setup-python@",
        'pip install -e ".[dev]"',
    )
    documented_actions = re.findall(
        r"^\s*uses:\s*([^\s#]+)",
        python_guide,
        re.MULTILINE,
    )

    # Then
    assert 'requires-python = "==3.9.25"' in python_guide
    assert 'target-version = "py39"' in python_guide
    assert 'target-version = "py311"' not in python_guide
    assert "uv sync --locked --extra dev" in python_guide
    assert "uv run --no-sync" in python_guide
    assert documented_actions
    assert all(
        re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference)
        for reference in documented_actions
    )
    assert not any(contract in python_guide for contract in stale_contracts)
    assert not re.search(r"^python -m devtools", lab_design, re.MULTILINE)
    assert "uv sync --locked --extra dev" in agents_guide
