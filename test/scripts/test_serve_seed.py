from __future__ import annotations

from pathlib import Path

from scripts import serve


class _CapturingLifecycle:
    def __init__(self) -> None:
        self.registrations: list[Path] = []

    def register_current_service(self, elfie_home: Path) -> None:
        self.registrations.append(elfie_home)


def test_managed_core_leaves_the_process_receipt_owned_by_its_supervisor(
    tmp_path: Path,
) -> None:
    lifecycle = _CapturingLifecycle()

    serve.register_service_process_for_start(
        lifecycle,
        tmp_path,
        managed_start=True,
    )

    assert lifecycle.registrations == []


def test_foreground_core_registers_its_own_process_receipt(tmp_path: Path) -> None:
    lifecycle = _CapturingLifecycle()

    serve.register_service_process_for_start(
        lifecycle,
        tmp_path,
        managed_start=False,
    )

    assert lifecycle.registrations == [tmp_path]
