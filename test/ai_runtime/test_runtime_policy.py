import pytest

from ai_runtime.policy.food_policy import RuntimeTaskType
from ai_runtime.safety.permissions import PermissionDeniedError, PermissionManager
from ai_runtime.usage.observer import RuntimeEventType, get_runtime_observer


class FakeConfig:
    runtime_policy = {
        "tool_permissions": {
            "RUN_SKILL": {"mode": "deny", "reason": "测试策略禁止运行技能"},
            "READ": {"mode": "allow", "reason": "只读放行"},
            "DELETE_SKILL": {"mode": "owner", "reason": "技能删除需要Owner令牌"},
        }
    }


def test_task_types_have_no_model_group_mapping():
    assert tuple(item.value for item in RuntimeTaskType) == (
        "chat",
        "reasoning",
        "vision",
        "code",
        "organize",
    )


def test_permission_manager_denies_and_records_policy_decision():
    observer = get_runtime_observer()
    observer.reset()
    manager = PermissionManager(FakeConfig())

    with pytest.raises(PermissionDeniedError) as exc_info:
        manager.verify_action("RUN_SKILL", file_path="code_sandbox")

    events = observer.snapshot()
    observer.reset()
    assert "测试策略禁止运行技能" in str(exc_info.value)
    assert events[-1].event_type == RuntimeEventType.PERMISSION_DECISION
    assert events[-1].subject == "RUN_SKILL"
    assert events[-1].status.value == "error"
    assert events[-1].metadata["mode"] == "deny"
    assert events[-1].metadata["allowed"] is False


def test_permission_manager_allows_owner_action_with_token():
    manager = PermissionManager(FakeConfig())
    manager._owner_token = "secret"

    assert manager.verify_action("DELETE_SKILL", file_path="old_skill.py", token="secret")


def test_permission_manager_denies_code_execution_by_default():
    manager = PermissionManager(object())

    with pytest.raises(PermissionDeniedError, match="策略禁止"):
        manager.verify_action("RUN_CODE", file_path="code_sandbox")
