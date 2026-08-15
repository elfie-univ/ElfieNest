from __future__ import annotations

from pathlib import Path

from scripts.serve import remaining_occupied_ports, select_implicit_service_ports


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


def test_implicit_defaults_move_as_a_pair_when_another_process_owns_them(
    tmp_path: Path,
) -> None:
    # Given: the conventional pair is occupied by an unrelated process.
    class Lifecycle:
        def ports_in_use(self, ports):
            if tuple(ports) == (8000, 8765):
                return [(8000, "external")]
            return []

        def existing_service_command(self, *_args):
            return None

    # When: the script was started without explicit port arguments.
    selected = select_implicit_service_ports(
        Lifecycle(),
        tmp_path,
        http_port=None,
        godot_ws_port=None,
    )

    # Then: HTTP and Godot move together, without taking over the external port.
    assert selected[0] != 8000
    assert selected[1] == selected[0] + 1


def test_explicit_port_keeps_strict_conflict_behavior(tmp_path: Path) -> None:
    # Given / When: the caller supplied a port explicitly.
    selected = select_implicit_service_ports(
        object(),
        tmp_path,
        http_port=8000,
        godot_ws_port=None,
    )

    # Then: implicit fallback is disabled for explicit configuration.
    assert selected == (8000, 8765)


def test_python_core_does_not_start_godot_processes() -> None:
    # Given
    source = (Path(__file__).resolve().parents[4] / "scripts" / "serve.py").read_text(
        encoding="utf-8"
    )

    # When / Then
    assert "start_godot_runtime(" not in source
    assert "Godot Web Runtime is hosted by ElfieNest Desktop" in source


def test_serve_main_does_not_rebind_nest_state_store_inside_worker() -> None:
    # Given
    source = (Path(__file__).resolve().parents[4] / "scripts" / "serve.py").read_text(
        encoding="utf-8"
    )

    # When / Then
    assert "from app.bootstrap.system_wiring.nest_session import (" in source
    assert "build_nest_session_services," in source
    assert "SQLiteNestStateRepository" not in source
    assert "engine.session.attach_state_store" not in source
