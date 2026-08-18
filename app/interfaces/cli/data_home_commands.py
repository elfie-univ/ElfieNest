"""CLI protocol for diagnosing and safely recovering a product data root."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.orchestration.lifecycle import (
    DataHomeInspection,
    DataHomeRecoveryError,
    LifecycleFacade,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def inspect_data_home_command(
    lifecycle: LifecycleFacade,
    *,
    explicit_home: str | None = None,
    json_output: bool = False,
) -> int:
    """Print a read-only data-root diagnosis before Runtime bootstrap."""
    inspection = lifecycle.inspect_data_home(
        explicit_home,
        project_root=_runtime_project_root(),
        runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
    )
    payload = _inspection_payload(inspection)
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"数据目录: {payload['home']}")
        print(f"状态: {payload['state']}")
        print(f"说明: {payload['detail']}")
    return 0


def recover_data_home_command(
    lifecycle: LifecycleFacade,
    *,
    explicit_home: str | None = None,
    json_output: bool = False,
) -> int:
    """Preserve a blocked root and activate a fresh root at the same path."""
    try:
        result = lifecycle.recover_data_home(
            explicit_home,
            project_root=_runtime_project_root(),
            runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
        )
    except DataHomeRecoveryError as error:
        payload = {
            "error_code": "data_home_recovery_failed",
            "error": str(error),
        }
        if json_output:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(f"❌ {error}")
        return 1
    payload = {
        "home": str(result.home),
        "backup_home": str(result.backup_home),
        "state": "recovered",
    }
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"✅ 已创建新数据环境: {payload['home']}")
        print(f"旧数据已保留在: {payload['backup_home']}")
    return 0


def _runtime_project_root() -> Path:
    configured = os.environ.get("ELFIENEST_PROJECT_ROOT")
    return Path(configured).resolve() if configured else PROJECT_ROOT


def _inspection_payload(inspection: DataHomeInspection) -> dict[str, object]:
    return {
        "state": inspection.state.value,
        "home": str(inspection.home),
        "detail": inspection.detail,
        "recoverable": inspection.recoverable,
    }


__all__ = (
    "inspect_data_home_command",
    "recover_data_home_command",
)
