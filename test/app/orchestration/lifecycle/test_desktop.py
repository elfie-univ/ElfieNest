from pathlib import Path
from typing import cast

from app.orchestration.lifecycle import desktop
from app.orchestration.lifecycle.ports import DesktopHostPort
from app.orchestration.lifecycle.types import ServiceLifecycleResult


class AbsentDesktopHost:
    def process_id(self, elfie_home: Path):
        return None


def test_stop_desktop_is_idempotent_without_pid_receipt(tmp_path: Path) -> None:
    result = desktop.stop_desktop_application(
        tmp_path, host=cast(DesktopHostPort, AbsentDesktopHost())
    )

    assert result == ServiceLifecycleResult(status="already_stopped")
