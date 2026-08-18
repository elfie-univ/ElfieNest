from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_normal_submit_gate_has_no_godot_startup_entrypoint() -> None:
    gate = (PROJECT_ROOT / "scripts" / "pre_submit_gate.sh").read_text(encoding="utf-8")

    assert "godot_guard.py" not in gate
    assert "Godot.app" not in gate
    assert "build_godot" not in gate


def test_toolchain_callers_delegate_project_execution_to_shared_runner() -> None:
    source_paths = (
        PROJECT_ROOT / "scripts" / "godot_species_validation.py",
        PROJECT_ROOT / "scripts" / "build_godot_dedicated.py",
        PROJECT_ROOT / "infrastructure" / "godot" / "artifacts" / "web_build.py",
        PROJECT_ROOT
        / ".agents"
        / "skills"
        / "godot-project-operator"
        / "scripts"
        / "godot_guard.py",
    )

    for path in source_paths:
        text = path.read_text(encoding="utf-8")
        assert "run_headless" in text, path
        assert "subprocess.Popen" not in text, path
        assert '[str(binary), "--headless"' not in text, path


def test_bootstrap_delegates_version_probes_to_shared_runner() -> None:
    bootstrap = (
        PROJECT_ROOT / "scripts" / "bootstrap_runtime_dependencies.sh"
    ).read_text(encoding="utf-8")

    assert "infrastructure.godot.runner" in bootstrap
    assert '"$binary" --version' not in bootstrap
