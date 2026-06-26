from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_install_script_bootstraps_project_venv() -> None:
    script = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

    assert "ensure_project_venv" in script
    assert '-m venv "$PROJECT_ROOT/.venv"' in script
    assert "-m pip install" in script
    assert '"$PROJECT_ROOT/requirements.txt"' in script
    assert "INSTALL_LOG_PATH" in script


def test_elfie_entrypoint_can_self_repair_missing_venv_dependencies() -> None:
    script = (PROJECT_ROOT / "elfie.sh").read_text(encoding="utf-8")

    assert "repair_project_venv" in script
    assert "ELFIE_SKIP_AUTO_REPAIR" in script
    assert "install.sh" in script
