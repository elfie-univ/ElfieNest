from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from infrastructure.tools.observation import (
    PermissionDecisionObservation,
    ToolCallObservation,
)
from infrastructure.tools.permissions import PermissionDeniedError, PermissionManager


@dataclass
class RecordingObservationPort:
    permissions: list[PermissionDecisionObservation] = field(default_factory=list)

    def record_tool_observation(self, observation: ToolCallObservation) -> None:
        pass

    def record_permission_observation(
        self, observation: PermissionDecisionObservation
    ) -> None:
        self.permissions.append(observation)


def test_permission_manager_preserves_default_read_policy_and_observation() -> None:
    observer = RecordingObservationPort()
    manager = PermissionManager(SimpleNamespace(runtime_policy={}), observer)

    assert manager.verify_action("READ", file_path="runtime_workspace") is True
    assert observer.permissions == [
        PermissionDecisionObservation(
            action="READ",
            resource="runtime_workspace",
            allowed=True,
            mode="allow",
            reason="只读工具自动放行",
        )
    ]


def test_permission_manager_preserves_unknown_action_denial() -> None:
    observer = RecordingObservationPort()
    manager = PermissionManager(SimpleNamespace(runtime_policy={}), observer)

    with pytest.raises(PermissionDeniedError, match="未知高危行为"):
        manager.verify_action("RUN_SKILL", file_path="unsafe")

    assert observer.permissions[-1].allowed is False
    assert observer.permissions[-1].mode == "deny"


def test_permission_manager_preserves_create_skill_path_escape_guard() -> None:
    observer = RecordingObservationPort()
    manager = PermissionManager(SimpleNamespace(runtime_policy={}), observer)

    with pytest.raises(PermissionDeniedError, match="路径审计拦截"):
        manager.verify_action("CREATE_SKILL", file_path="../escape.py")

    assert observer.permissions[-1].resource == "../escape.py"
    assert observer.permissions[-1].allowed is False
