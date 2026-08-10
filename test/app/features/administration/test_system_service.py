from __future__ import annotations

from app.features.administration.system_service import (
    default_port_statuses,
    service_port_statuses,
)


def test_default_port_statuses_include_application_services(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    def fake_check_port(port: int, name: str):
        calls.append((port, name))
        return None

    monkeypatch.setattr(
        "app.features.administration.system_service.check_port", fake_check_port
    )

    default_port_statuses()

    assert calls == [
        (8000, "HTTP"),
        (8766, "WebSocket (admin)"),
        (8765, "WebSocket (Godot)"),
    ]


def test_service_port_statuses_uses_custom_http_and_ws_ports(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    def fake_check_port(port: int, name: str):
        calls.append((port, name))
        return None

    monkeypatch.setattr(
        "app.features.administration.system_service.check_port", fake_check_port
    )

    service_port_statuses(8100, 8866, 8768)

    assert calls == [
        (8100, "HTTP"),
        (8866, "WebSocket (admin)"),
        (8768, "WebSocket (Godot)"),
    ]
