from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
AUTHORITY_RELATIVE_PATH = "infrastructure/godot/lifecycle/electron/authority_main.mjs"
AUTHORITY_MAIN = PROJECT_ROOT / AUTHORITY_RELATIVE_PATH
HOST_MAIN = PROJECT_ROOT / "app/bootstrap/desktop_host/host_main.mjs"
HOST_CONFIG = PROJECT_ROOT / "app/bootstrap/desktop_host/electron-builder.yml"


def test_hidden_authority_window_has_a_process_lifetime_reference() -> None:
    source = AUTHORITY_MAIN.read_text(encoding="utf-8")

    declaration = source.index("let authorityWindow")
    ready_callback = source.index("app.whenReady()")

    assert declaration < ready_callback
    assert "authorityWindow = new BrowserWindow" in source


def test_bootstrap_host_loads_and_packages_the_authority_entrypoint() -> None:
    package_source = (PROJECT_ROOT / "app/interfaces/desktop/package.json").read_text(
        encoding="utf-8"
    )
    main_source = (PROJECT_ROOT / "app/interfaces/desktop/src/main.ts").read_text(
        encoding="utf-8"
    )
    host_source = HOST_MAIN.read_text(encoding="utf-8")
    host_config = HOST_CONFIG.read_text(encoding="utf-8")

    assert "infrastructure/godot/lifecycle/electron" not in package_source
    assert "godot-authority" not in main_source
    assert "authority_main.mjs" not in main_source
    assert "ELFIENEST_LIFECYCLE_COMMAND" not in main_source
    assert "authority_main.mjs" in host_source
    assert "infrastructure/godot/lifecycle/electron" in host_config
