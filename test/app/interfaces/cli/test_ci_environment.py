from __future__ import annotations

import re

from test.support.paths import PROJECT_ROOT

PINNED_CPYTHON_VERSION = "3.9.25"


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
    permissions = re.search(
        r"^permissions:\s*\n(?P<entries>(?:\s{2}[a-z-]+:\s+\w+\s*\n?)+)",
        workflow,
        re.MULTILINE,
    )
    values = (
        re.findall(r"^\s{2}[a-z-]+:\s+(\w+)\s*$", permissions["entries"], re.MULTILINE)
        if permissions
        else []
    )

    # Then
    assert values
    assert set(values) == {"read"}


def test_documentation_does_not_recommend_privileged_installation() -> None:
    # Given
    tooling_guide = (
        PROJECT_ROOT / "docs" / "developer" / "engineering" / "tooling.md"
    ).read_text(encoding="utf-8")

    # When
    recommends_sudo_install = bool(re.search(r"sudo\s+\./install\.sh", tooling_guide))

    # Then
    assert not recommends_sudo_install


def test_engineering_guides_use_the_locked_environment_contract() -> None:
    # Given
    project_config = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    contributing_guide = (PROJECT_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    agents_guide = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    tooling_guide = (
        PROJECT_ROOT / "docs" / "developer" / "engineering" / "tooling.md"
    ).read_text(encoding="utf-8")

    # When
    stale_contracts = (
        'requires-python = ">=3.9,<3.10"',
        "actions/setup-python@",
        'pip install -e ".[dev]"',
    )
    engineering_guides = contributing_guide + agents_guide + tooling_guide

    # Then
    assert 'requires-python = "==3.9.25"' in project_config
    assert 'target-version = "py39"' in project_config
    assert 'target-version = "py311"' not in project_config
    # Bootstrap-based dependency management instead of direct uv sync
    assert "bootstrap.sh" in contributing_guide
    assert "bootstrap.sh" in agents_guide
    assert "uv run --no-sync" in contributing_guide
    assert "uv run --no-sync" in agents_guide
    assert "./developer.sh" in tooling_guide
    assert not re.search(r"^python -m devtools", tooling_guide, re.MULTILINE)
    assert not any(contract in engineering_guides for contract in stale_contracts)


def test_ci_installs_and_verifies_exact_cpython_runtime() -> None:
    # Given
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    # When
    literal_install = "uv python install " + PINNED_CPYTHON_VERSION
    variable_install = 'uv python install "$PYTHON_VERSION"'
    runtime_probe = re.compile(
        r'sys\.implementation\.name == "cpython"\s+and\s+'
        r'platform\.python_version\(\) == "3\.9\.25"'
    )

    # Then
    install_count = workflow.count(literal_install) + workflow.count(variable_install)
    assert install_count >= 4
    if variable_install in workflow:
        assert f'PYTHON_VERSION: "{PINNED_CPYTHON_VERSION}"' in workflow
    assert runtime_probe.search(workflow)
