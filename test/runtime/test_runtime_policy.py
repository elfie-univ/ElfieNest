import pytest

from runtime.models.groups import load_model_groups
from runtime.policy.food_policy import load_food_policy, resolve_food_policy
from runtime.safety.permissions import PermissionDeniedError, PermissionManager
from runtime.usage.observer import RuntimeEventType, get_runtime_observer


class FakeConfig:
    runtime_policy = {
        "model_groups": {
            "premium": {
                "display_name": "精粮",
                "model_keys": ["remote_deep", "remote_cheap", "local_fast"],
            }
        },
        "task_routes": {
            "reasoning": "premium",
            "code": "premium",
        },
        "tool_permissions": {
            "RUN_SKILL": {
                "mode": "deny",
                "reason": "测试策略禁止运行技能",
            },
            "READ": {
                "mode": "allow",
                "reason": "只读放行",
            },
            "DELETE_SKILL": {
                "mode": "admin",
                "reason": "技能删除需要管理员令牌",
            },
        },
    }


def test_runtime_policy_overrides_model_groups_and_task_routes():
    policy = load_food_policy(FakeConfig.runtime_policy)
    model_groups = load_model_groups(FakeConfig.runtime_policy)

    decision = resolve_food_policy(
        task_type="reasoning",
        available_model_keys={"remote_cheap", "local_fast"},
        food_policy=policy,
        model_groups=model_groups,
    )

    assert decision.group_key == "premium"
    assert decision.model_key == "remote_cheap"


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


def test_runtime_policy_ignores_unknown_task_route_and_falls_back_unknown_group():
    policy = load_food_policy(
        {
            "task_routes": {
                "unknown": "premium",
                "reasoning": "missing_group",
            }
        }
    )

    decision = resolve_food_policy(
        task_type="reasoning",
        available_model_keys={"local_fast"},
        food_policy=policy,
        model_groups=load_model_groups({}),
    )

    assert "unknown" not in {task_type.value for task_type in policy.task_groups}
    assert decision.group_key == "coarse"
    assert decision.model_key == "local_fast"


def test_permission_manager_allows_admin_action_with_token():
    manager = PermissionManager(FakeConfig())
    manager._admin_token = "secret"

    assert (
        manager.verify_action(
            "DELETE_SKILL",
            file_path="old_skill.py",
            token="secret",
        )
        is True
    )
