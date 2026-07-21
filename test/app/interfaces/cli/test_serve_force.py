from __future__ import annotations

from pathlib import Path

from scripts.e2e_dashboard_check import find_distinct_free_ports
from scripts.serve import remaining_occupied_ports


def test_force_cleanup_reports_ports_still_occupied() -> None:
    # Given
    occupied = ((8000, "HTTP"), (8766, "WebSocket"), (8765, "Godot WebSocket"))

    # When
    remaining = remaining_occupied_ports(
        occupied,
        lambda port: port in {8766, 8765},
    )

    # Then
    assert remaining == [(8766, "WebSocket"), (8765, "Godot WebSocket")]


def test_dashboard_e2e_uses_distinct_service_ports() -> None:
    ports = find_distinct_free_ports(3)

    assert len(ports) == 3
    assert len(set(ports)) == 3


def test_python_core_does_not_start_godot_processes() -> None:
    # Given
    source = (Path(__file__).resolve().parents[4] / "scripts" / "serve.py").read_text(
        encoding="utf-8"
    )

    # When / Then
    assert "start_godot_runtime(" not in source
    assert "Godot Web Runtime 由 ElfieNest Desktop" in source
