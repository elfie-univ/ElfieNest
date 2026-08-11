from __future__ import annotations

from pathlib import Path

from scripts.serve import remaining_occupied_ports


def test_force_cleanup_reports_ports_still_occupied() -> None:
    # Given
    occupied = ((8000, "HTTP"), (8765, "Godot WebSocket"))

    # When
    remaining = remaining_occupied_ports(
        occupied,
        lambda port: port == 8765,
    )

    # Then
    assert remaining == [(8765, "Godot WebSocket")]


def test_python_core_does_not_start_godot_processes() -> None:
    # Given
    source = (Path(__file__).resolve().parents[4] / "scripts" / "serve.py").read_text(
        encoding="utf-8"
    )

    # When / Then
    assert "start_godot_runtime(" not in source
    assert "Godot Web Runtime is hosted by ElfieNest Desktop" in source


def test_serve_main_does_not_rebind_nest_repository_inside_worker() -> None:
    # Given
    source = (Path(__file__).resolve().parents[4] / "scripts" / "serve.py").read_text(
        encoding="utf-8"
    )

    # When / Then
    assert "from app.bootstrap.system_wiring.nest_session import (" in source
    assert "build_nest_session_services," in source
    assert "SQLiteNestStateRepository" not in source
    assert "engine.session.attach_repository" not in source
