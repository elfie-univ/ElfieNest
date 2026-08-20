"""Lifecycle owns user-visible service-port observations."""

from pathlib import Path
from unittest.mock import Mock, call

from app.orchestration.lifecycle import LifecycleFacade
from app.orchestration.lifecycle.ports import DoctorRepairResult
from app.orchestration.lifecycle.runtime_snapshot import (
    EndpointSnapshot,
    RuntimePhase,
    RuntimeSnapshotV1,
)


def test_service_port_statuses_use_injected_process_port() -> None:
    process = Mock()
    process.ports_in_use.side_effect = lambda ports: ports[0] in {8100, 8768}
    lifecycle = LifecycleFacade(
        service_launch_command=("/managed/core",),
        process_port=process,
        recovery_lock=Mock(),
        desktop_host=Mock(),
        http_probe=Mock(),
        runtime_record_factory=Mock(),
        authority_host_factory=Mock(),
    )

    statuses = lifecycle.service_port_statuses(8100, 8768)

    assert [(item.port, item.name, item.running) for item in statuses] == [
        (8100, "HTTP", True),
        (8768, "WebSocket (Godot)", True),
    ]
    assert process.ports_in_use.call_args_list == [
        call((8100,)),
        call((8768,)),
    ]


def test_optional_runtime_component_stays_behind_lifecycle_facade() -> None:
    optional_component = Mock()
    optional_component.ready.return_value = True
    lifecycle = LifecycleFacade(
        service_launch_command=("/managed/core",),
        process_port=Mock(),
        recovery_lock=Mock(),
        desktop_host=Mock(),
        http_probe=Mock(),
        runtime_record_factory=Mock(),
        authority_host_factory=Mock(),
        optional_component=optional_component,
    )

    assert lifecycle.optional_component_ready() is True
    lifecycle.prepare_optional_component()

    optional_component.ready.assert_called_once_with()
    optional_component.prepare.assert_called_once_with()


def test_default_service_command_uses_the_injected_launch_target() -> None:
    lifecycle = LifecycleFacade(
        service_launch_command=("/managed/core",),
        process_port=Mock(),
        recovery_lock=Mock(),
        desktop_host=Mock(),
        http_probe=Mock(),
        runtime_record_factory=Mock(),
        authority_host_factory=Mock(),
    )

    assert lifecycle.default_service_command(("--lan", "--force")) == (
        "/managed/core",
        "--lan",
        "--force",
    )
    assert lifecycle.is_managed_service_command(("/managed/core", "--lan")) is True
    assert lifecycle.is_managed_service_command(("/other/core", "--lan")) is False


def test_frontend_preparation_stays_behind_lifecycle_facade() -> None:
    frontend = Mock()
    godot_web = Mock()
    godot_web.prepare.return_value = True
    lifecycle = LifecycleFacade(
        service_launch_command=("/managed/core",),
        process_port=Mock(),
        recovery_lock=Mock(),
        desktop_host=Mock(),
        http_probe=Mock(),
        runtime_record_factory=Mock(),
        authority_host_factory=Mock(),
        frontend_preparation=frontend,
        godot_web_preparation=godot_web,
    )

    lifecycle.prepare_frontend("development")

    frontend.prepare.assert_called_once_with("development")
    assert lifecycle.prepare_godot_web("release", is_frozen=True) is True
    godot_web.prepare.assert_called_once_with("release", is_frozen=True)


def test_core_endpoint_publication_updates_the_authoritative_starting_snapshot() -> (
    None
):
    record = Mock()
    record.read.return_value = RuntimeSnapshotV1(
        instance_id="instance",
        phase=RuntimePhase.CORE_STARTING,
        revision=4,
    )
    lifecycle = LifecycleFacade(
        service_launch_command=("/managed/core",),
        process_port=Mock(),
        recovery_lock=Mock(),
        desktop_host=Mock(),
        http_probe=Mock(),
        runtime_record_factory=lambda _home: record,
        authority_host_factory=Mock(),
    )
    endpoints = (
        EndpointSnapshot("http", "http", "127.0.0.1", 12421),
        EndpointSnapshot("godot_ws", "ws", "127.0.0.1", 12422),
    )

    lifecycle.publish_core_endpoints(Path("/tmp/elfienest"), endpoints)

    published = record.write.call_args.args[0]
    assert published.revision == 5
    assert published.phase is RuntimePhase.CORE_STARTING
    assert published.endpoints == endpoints


def test_doctor_repair_reconciles_shared_optional_orphans() -> None:
    doctor = Mock()
    doctor.repair_local_state.return_value = DoctorRepairResult(("receipt",))
    optional_component = Mock()
    optional_component.reconcile_orphaned_services.return_value = ("ollama",)
    data_home = Mock()
    data_home.home.return_value = Path("/selected")
    lifecycle = LifecycleFacade(
        service_launch_command=("/managed/core",),
        process_port=Mock(),
        recovery_lock=Mock(),
        desktop_host=Mock(),
        http_probe=Mock(),
        runtime_record_factory=Mock(),
        authority_host_factory=Mock(),
        optional_component=optional_component,
        doctor=doctor,
        data_home=data_home,
    )

    result = lifecycle.repair_local_state()

    assert result == DoctorRepairResult(("receipt", "ollama"))
    optional_component.reconcile_orphaned_services.assert_called_once_with(
        elfie_home=Path("/selected")
    )
