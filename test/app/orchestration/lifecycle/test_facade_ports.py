"""Lifecycle owns user-visible service-port observations."""

from unittest.mock import Mock, call

from app.orchestration.lifecycle import LifecycleFacade


def test_service_port_statuses_use_injected_process_port() -> None:
    process = Mock()
    process.ports_in_use.side_effect = lambda ports: ports[0] in {8100, 8768}
    lifecycle = LifecycleFacade(
        process_port=process,
        recovery_lock=Mock(),
        desktop_host=Mock(),
        http_probe=Mock(),
        runtime_record_factory=Mock(),
        authority_host_factory=Mock(),
    )

    statuses = lifecycle.service_port_statuses(8100, 8866, 8768)

    assert [(item.port, item.name, item.running) for item in statuses] == [
        (8100, "HTTP", True),
        (8866, "WebSocket (admin)", False),
        (8768, "WebSocket (Godot)", True),
    ]
    assert process.ports_in_use.call_args_list == [
        call((8100,)),
        call((8866,)),
        call((8768,)),
    ]
