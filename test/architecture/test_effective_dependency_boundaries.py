"""Machine gates for imports hidden behind process and dynamic-load APIs."""

from __future__ import annotations

from pathlib import Path

from scripts.architecture.effective_dependency_scan import (
    RULE_LEDGER_IDS,
    collect_effective_dependency_violations,
    deny_all_failures,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _write(root: Path, relative: str, source: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def test_repository_has_no_forbidden_effective_dependencies() -> None:
    violations = collect_effective_dependency_violations(PROJECT_ROOT)

    assert set(violations) == set(RULE_LEDGER_IDS)
    assert deny_all_failures(violations) == []


def test_python_process_targets_follow_the_callers_boundary(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "app/interfaces/cli/command.py",
        "import subprocess\n"
        "subprocess.run(['python', '-m', 'infrastructure.models.probe'])\n",
    )
    _write(
        tmp_path,
        "scripts/elfienest.py",
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-m', 'devtools.nest_lab'])\n",
    )

    violations = collect_effective_dependency_violations(tmp_path)

    assert violations["interface_effective_dependencies"] == frozenset(
        {
            "app/interfaces/cli/command.py:2 [subprocess.run] "
            "-> infrastructure.models.probe"
        }
    )
    assert violations["production_tooling_effective_dependencies"] == frozenset(
        {"scripts/elfienest.py:2 [subprocess.run] -> devtools.nest_lab"}
    )


def test_dynamic_imports_and_script_paths_cannot_bypass_layers(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "elfie/brain/loader.py",
        "import importlib\nimportlib.import_module('nest.world.state')\n",
    )
    _write(
        tmp_path,
        "app/features/setup/runner.py",
        "import subprocess\nsubprocess.run(['python', 'scripts/serve.py'])\n",
    )

    violations = collect_effective_dependency_violations(tmp_path)

    assert violations["elfie_effective_dependencies"] == frozenset(
        {"elfie/brain/loader.py:2 [importlib.import_module] -> nest.world.state"}
    )
    assert violations["feature_effective_dependencies"] == frozenset(
        {"app/features/setup/runner.py:2 [subprocess.run] -> scripts.serve"}
    )


def test_node_and_shell_literal_targets_use_the_same_policy(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "app/interfaces/desktop/runner.ts",
        "execFile(\n  'python',\n  ['-m', 'infrastructure.models.probe'],\n);\n",
    )
    _write(
        tmp_path,
        "app/orchestration/lifecycle/runner.sh",
        "python -m infrastructure.platform.lifecycle.process\n",
    )

    violations = collect_effective_dependency_violations(tmp_path)

    assert violations["interface_effective_dependencies"] == frozenset(
        {"app/interfaces/desktop/runner.ts:1 [execFile] -> infrastructure.models.probe"}
    )
    assert violations["orchestration_effective_dependencies"] == frozenset(
        {
            "app/orchestration/lifecycle/runner.sh:1 [shell] "
            "-> infrastructure.platform.lifecycle.process"
        }
    )


def test_allowed_composition_and_lab_targets_remain_valid(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "app/bootstrap/launcher.py",
        "import subprocess\nsubprocess.run(['python', 'scripts/serve.py'])\n",
    )
    _write(
        tmp_path,
        "devtools/elfie_lab/launcher.py",
        "import subprocess\nsubprocess.run(['python', '-m', 'devtools.nest_lab'])\n",
    )

    violations = collect_effective_dependency_violations(tmp_path)

    assert deny_all_failures(violations) == []


def test_godot_and_unknown_source_roots_are_fail_closed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "godot_project/tools/runner.gd",
        'OS.execute("python", ["-m", "app.interfaces.cli.command"])\n',
    )
    _write(
        tmp_path,
        "new_surface/runner.sh",
        "python -m elfie.brain.runtime\n",
    )

    violations = collect_effective_dependency_violations(tmp_path)

    assert violations["production_tooling_effective_dependencies"] == frozenset(
        {
            "godot_project/tools/runner.gd:1 [execute] -> app.interfaces.cli.command",
            "new_surface/runner.sh:1 [shell] -> elfie.brain.runtime",
        }
    )
