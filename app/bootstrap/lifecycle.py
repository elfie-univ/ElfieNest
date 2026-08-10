"""Production composition for the App Runtime lifecycle boundary."""

from __future__ import annotations

from app.orchestration.lifecycle import LifecycleFacade
from infrastructure.godot.lifecycle.authority import GodotAuthorityHostAdapter
from infrastructure.platform.lifecycle.desktop import LocalDesktopHostAdapter
from infrastructure.platform.lifecycle.http_probe import UrllibHttpProbeAdapter
from infrastructure.platform.lifecycle.process import LocalServiceProcessAdapter
from infrastructure.platform.lifecycle.recovery_lock import LocalRecoveryLockAdapter
from infrastructure.platform.lifecycle.runtime_record import FileRuntimeRecordAdapter


def create_lifecycle_facade() -> LifecycleFacade:
    """Create one process-scoped lifecycle facade with explicit Adapter injection."""
    return LifecycleFacade(
        process_port=LocalServiceProcessAdapter(),
        recovery_lock=LocalRecoveryLockAdapter(),
        desktop_host=LocalDesktopHostAdapter(),
        http_probe=UrllibHttpProbeAdapter(),
        runtime_record_factory=FileRuntimeRecordAdapter,
        authority_host_factory=GodotAuthorityHostAdapter,
    )
