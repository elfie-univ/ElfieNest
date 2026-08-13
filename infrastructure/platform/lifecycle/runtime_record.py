"""Atomic file adapter for the lifecycle owner-generation record."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Final

from app.orchestration.lifecycle.runtime_health import (
    ComponentHealth,
    OwnerLease,
    RuntimeComponent,
    RuntimeHealth,
    RuntimeHealthState,
)

RUNTIME_RECORD_FILENAME: Final = "runtime.json"


class FileRuntimeRecordAdapter:
    """Read and atomically write the validated lifecycle Runtime record."""

    def __init__(self, elfie_home: Path) -> None:
        self._elfie_home = elfie_home

    def read(self) -> RuntimeHealth:
        try:
            payload = json.loads(self._record_path().read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return self._failed_record()
            generation = payload["generation"]
            owner_id = payload.get("owner_id")
            startup_owner_id = payload.get("startup_owner_id")
            state = RuntimeHealthState(payload["state"])
            raw_components = payload["components"]
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError):
            return self._empty_record()
        if not isinstance(generation, int) or generation < 0:
            return self._failed_record()
        if startup_owner_id == "":
            startup_owner_id = None
        if startup_owner_id is not None and not isinstance(startup_owner_id, str):
            return self._failed_record()
        if not isinstance(raw_components, list):
            return self._failed_record()
        components: list[ComponentHealth] = []
        try:
            for raw_component in raw_components:
                if not isinstance(raw_component, dict):
                    return self._failed_record()
                detail = raw_component.get("detail", "")
                pid = raw_component.get("pid")
                if not isinstance(detail, str):
                    return self._failed_record()
                if pid is not None and (
                    not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0
                ):
                    return self._failed_record()
                components.append(
                    ComponentHealth(
                        component=RuntimeComponent(raw_component["component"]),
                        state=RuntimeHealthState(raw_component["state"]),
                        detail=detail,
                        pid=pid,
                    )
                )
        except (KeyError, TypeError, ValueError):
            return self._failed_record()
        owner_lease = (
            OwnerLease(owner_id=owner_id, generation=generation)
            if isinstance(owner_id, str) and owner_id != "" and generation > 0
            else None
        )
        return RuntimeHealth(
            state=state,
            generation=generation,
            owner_lease=owner_lease,
            components=tuple(components),
            startup_owner_id=startup_owner_id,
        )

    def write(self, health: RuntimeHealth) -> None:
        self._elfie_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        runtime_dir = self._elfie_home / "runtime"
        runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".runtime.", dir=str(runtime_dir)
        )
        temporary_path = Path(temporary_name)
        payload = json.dumps(
            {
                "generation": health.generation,
                "owner_id": health.owner_lease.owner_id if health.owner_lease else "",
                "startup_owner_id": health.startup_owner_id or "",
                "state": health.state.value,
                "components": [
                    {
                        "component": component.component.value,
                        "state": component.state.value,
                        "detail": component.detail,
                        "pid": component.pid,
                    }
                    for component in health.components
                ],
            },
            sort_keys=True,
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as receipt:
                receipt.write(payload)
            temporary_path.replace(self._record_path())
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise

    def remove(self) -> None:
        self._record_path().unlink(missing_ok=True)

    def _record_path(self) -> Path:
        return self._elfie_home / "runtime" / RUNTIME_RECORD_FILENAME

    @staticmethod
    def _empty_record() -> RuntimeHealth:
        return RuntimeHealth(
            state=RuntimeHealthState.STOPPED,
            generation=0,
            owner_lease=None,
            components=(),
        )

    @staticmethod
    def _failed_record() -> RuntimeHealth:
        return RuntimeHealth(
            state=RuntimeHealthState.FAILED,
            generation=0,
            owner_lease=None,
            components=(),
        )
