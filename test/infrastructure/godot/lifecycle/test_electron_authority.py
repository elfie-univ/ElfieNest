from __future__ import annotations

import subprocess
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
    assert 'process.once("SIGTERM"' in source
    assert 'process.once("SIGINT"' in source
    assert "authorityWindow.close()" in source
    assert "app.exit(exitCode)" in source
    assert "process.exit(exitCode)" in source


def test_hidden_authority_records_process_and_electron_crash_surfaces() -> None:
    source = AUTHORITY_MAIN.read_text(encoding="utf-8")

    assert 'process.on("uncaughtExceptionMonitor"' in source
    assert 'process.on("unhandledRejection"' in source
    assert 'app.on("render-process-gone"' in source
    assert 'app.on("child-process-gone"' in source
    assert 'authorityWindow.on("unresponsive"' in source
    assert '"did-fail-load"' in source
    assert "requestShutdown(1" in source
    assert "ELFIENEST_AUTHORITY_LOG" in source
    assert "appendFileSync" in source
    assert "AUTHORITY_LOG_MAX_BYTES" in source
    assert '"console-message"' in source
    assert "preventDefault()" in source
    assert "crash_reporter_start_failed" in source
    assert "redactDiagnosticText(errorDescription).slice(0, 2048)" in source
    assert 'emitDiagnostic("authority_window_unresponsive", "warning")' in source
    assert 'requestShutdown(12, "renderer_unresponsive")' not in source
    assert "AUTHORITY_UNRESPONSIVE_GRACE_MS" not in source
    assert "parsed.total_attempts" in source
    assert "sampledRendererDiagnostic" in source
    assert "suppressed_count" in source


def test_hidden_authority_redacts_oauth_credentials_and_authorization_headers() -> None:
    source = AUTHORITY_MAIN.read_text(encoding="utf-8")
    function_start = source.index("function redactDiagnosticText")
    function_end = source.index("\nfunction diagnosticError", function_start)
    script = (
        source[function_start:function_end]
        + "\nprocess.stdout.write(redactDiagnosticText(process.argv[1]));"
    )
    credential_text = (
        "access_token=sample-access "
        "refresh_token='sample-refresh' "
        '"client_secret": "sample-client" '
        "Authorization: Bearer sample-bearer "
        "Bearer sample-standalone"
    )

    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script, credential_text],
        check=True,
        capture_output=True,
        text=True,
    )

    for credential in (
        "sample-access",
        "sample-refresh",
        "sample-client",
        "sample-bearer",
        "sample-standalone",
    ):
        assert credential not in completed.stdout


def test_hidden_authority_exits_when_its_core_process_dies() -> None:
    source = AUTHORITY_MAIN.read_text(encoding="utf-8")

    assert "ELFIENEST_CORE_PID" in source
    assert "process.kill(corePid, 0)" in source
    assert "CORE_LIVENESS_CHECK_INTERVAL_MS" in source
    assert 'requestShutdown(2, "core_process_exited")' in source


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
