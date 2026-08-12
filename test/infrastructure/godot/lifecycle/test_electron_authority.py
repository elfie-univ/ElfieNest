from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
AUTHORITY_RELATIVE_PATH = "infrastructure/godot/lifecycle/electron/authority_main.mjs"
AUTHORITY_MAIN = PROJECT_ROOT / AUTHORITY_RELATIVE_PATH


def test_hidden_authority_window_has_a_process_lifetime_reference() -> None:
    source = AUTHORITY_MAIN.read_text(encoding="utf-8")

    declaration = source.index("let authorityWindow")
    ready_callback = source.index("app.whenReady()")

    assert declaration < ready_callback
    assert "authorityWindow = new BrowserWindow" in source


def test_desktop_loads_and_packages_the_moved_authority_entrypoint() -> None:
    package_source = (PROJECT_ROOT / "app/interfaces/desktop/package.json").read_text(
        encoding="utf-8"
    )
    main_source = (PROJECT_ROOT / "app/interfaces/desktop/src/main.ts").read_text(
        encoding="utf-8"
    )

    assert (
        '"from": "../../../infrastructure/godot/lifecycle/electron"' in package_source
    )
    assert '"to": "infrastructure/godot/lifecycle/electron"' in package_source
    assert '"godot_runtime", "electron", "authority_main.mjs"' not in main_source
    for segment in (
        '"infrastructure"',
        '"godot"',
        '"lifecycle"',
        '"electron"',
        '"authority_main.mjs"',
    ):
        assert main_source.count(segment) >= 2
