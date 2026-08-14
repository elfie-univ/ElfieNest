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


def test_hidden_macos_authority_does_not_occupy_the_dock() -> None:
    source = AUTHORITY_MAIN.read_text(encoding="utf-8")

    assert 'process.platform === "darwin"' in source
    assert "app.dock.hide()" in source


def test_hidden_authority_retries_core_load_and_handles_owned_shutdown() -> None:
    source = AUTHORITY_MAIN.read_text(encoding="utf-8")

    assert "AUTHORITY_LOAD_MAX_ATTEMPTS" in source
    assert "loadAuthorityWindow" in source
    assert 'process.once("SIGTERM", requestShutdown)' in source
    assert 'process.once("SIGINT", requestShutdown)' in source
    assert "authorityWindow.close()" in source
    assert "app.exit(0)" in source
    assert "process.exit(0)" in source


def test_hidden_authority_exits_when_its_core_process_dies() -> None:
    source = AUTHORITY_MAIN.read_text(encoding="utf-8")

    assert "ELFIENEST_CORE_PID" in source
    assert "process.kill(corePid, 0)" in source
    assert "CORE_LIVENESS_CHECK_INTERVAL_MS" in source
    assert "requestShutdown()" in source


def test_hidden_authority_retries_a_short_single_instance_lock_race() -> None:
    source = AUTHORITY_MAIN.read_text(encoding="utf-8")

    assert "acquireAuthorityLock" in source
    assert "AUTHORITY_LOCK_RETRY" in source
    assert "await acquireAuthorityLock()" in source


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
    assert "from: packaged-resources" in host_config
    assert "icon: assets/elfienest-macos-app-icon.png" in host_config
    assert "icon: assets/elfienest-app-icon.png" in host_config
