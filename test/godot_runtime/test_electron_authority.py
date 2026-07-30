from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_MAIN = PROJECT_ROOT / "godot_runtime/electron/authority_main.mjs"


def test_hidden_authority_window_has_a_process_lifetime_reference() -> None:
    source = AUTHORITY_MAIN.read_text(encoding="utf-8")

    declaration = source.index("let authorityWindow")
    ready_callback = source.index("app.whenReady()")

    assert declaration < ready_callback
    assert "authorityWindow = new BrowserWindow" in source
