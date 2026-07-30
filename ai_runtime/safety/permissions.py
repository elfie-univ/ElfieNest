from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ai_runtime.usage.observer import (
    PermissionDecisionObservation,
    get_runtime_observer,
)

logger = logging.getLogger("ai_runtime.safety.permissions")


class PermissionDeniedError(Exception):
    """大模型进行越权或高危敏感操作被底层物理防御阻断的异常"""

    pass


class PermissionMode(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"
    OWNER = "owner"


@dataclass(frozen=True)
class ToolPermissionRule:
    mode: PermissionMode
    reason: str


DEFAULT_TOOL_PERMISSIONS: Mapping[str, ToolPermissionRule] = {
    "WEB_SEARCH": ToolPermissionRule(PermissionMode.ALLOW, "联网检索工具自动放行"),
    "RUN_CODE": ToolPermissionRule(
        PermissionMode.DENY,
        "真实代码隔离尚未接入，生产环境默认禁止执行代码",
    ),
    "READ": ToolPermissionRule(PermissionMode.ALLOW, "只读工具自动放行"),
    "RUN_SKILL": ToolPermissionRule(PermissionMode.ALLOW, "运行已登记技能自动放行"),
    "LIST_SKILLS": ToolPermissionRule(PermissionMode.ALLOW, "读取技能清单自动放行"),
    "CREATE_SKILL": ToolPermissionRule(
        PermissionMode.ALLOW, "新增技能允许，但文件名必须留在技能根目录"
    ),
    "DELETE_SKILL": ToolPermissionRule(
        PermissionMode.OWNER, "技能删除或覆盖需要Owner令牌"
    ),
}


class PermissionManager:
    """策略性自动审计管理器，守护精灵自进化的物理边界"""

    def __init__(self, config):
        self.config = config
        # 定义夜间 N3 整理专用的系统高特权令牌
        # 可以从环境变量获取，或者在启动时随机生成一个以确保本地安全
        self._owner_token = os.getenv("ELFIE_OWNER_TOKEN", "").strip()

    def verify_action(
        self, action: str, file_path: str = None, token: str = None
    ) -> bool:
        """
        核心物理审计方法
        :param action: 操作类型 - "READ", "CREATE_SKILL", "RUN_SKILL", "DELETE_SKILL"
        :param file_path: 操作目标文件名或路径
        :param token: 操作时携带的特权令牌
        :return: True (审计通过)；失败则直接抛出 PermissionDeniedError
        """
        resource = file_path or ""
        logger.info("🛡️ 权限安全审计中... 行为: %s, 资源: %s", action, resource)

        if action == "CREATE_SKILL" and _has_path_escape(resource):
            reason = f"路径审计拦截，不允许跨越自定义技能根目录：'{resource}'"
            self._record_decision(
                action, resource, allowed=False, mode="deny", reason=reason
            )
            raise PermissionDeniedError(f"❌ {reason}")

        rule = self._rule_for(action)
        if rule.mode == PermissionMode.ALLOW:
            self._record_decision(
                action,
                resource,
                allowed=True,
                mode=rule.mode.value,
                reason=rule.reason,
            )
            return True
        if rule.mode == PermissionMode.OWNER:
            if (
                self._owner_token
                and token
                and secrets.compare_digest(token, self._owner_token)
            ):
                logger.info("🔑 [特权令牌校验通过] 允许执行离线技能库代谢与去重操作")
                self._record_decision(
                    action,
                    resource,
                    allowed=True,
                    mode=rule.mode.value,
                    reason=rule.reason,
                )
                return True
            reason = rule.reason or "该操作需要Owner令牌"
            self._record_decision(
                action,
                resource,
                allowed=False,
                mode=rule.mode.value,
                reason=reason,
            )
            raise PermissionDeniedError(
                f"❌ 越权执行被物理阻断！原因：{reason}\n"
                f"💡 技能代谢只允许在精灵 N3 深度睡眠模式下，由高特权整理模型（携带 owner_token）执行。"
            )
        if rule.mode == PermissionMode.ASK:
            reason = rule.reason or "该操作需要人工确认，当前运行链路未提供交互式审批"
            self._record_decision(
                action,
                resource,
                allowed=False,
                mode=rule.mode.value,
                reason=reason,
            )
            raise PermissionDeniedError(f"❌ 操作需要人工确认：{reason}")

        reason = rule.reason or "策略禁止该操作"
        self._record_decision(
            action,
            resource,
            allowed=False,
            mode=rule.mode.value,
            reason=reason,
        )
        raise PermissionDeniedError(f"❌ 策略禁止执行：{reason}")

    def _rule_for(self, action: str) -> ToolPermissionRule:
        runtime_policy = getattr(self.config, "runtime_policy", {})
        if isinstance(runtime_policy, Mapping):
            raw_permissions = runtime_policy.get("tool_permissions", {})
        else:
            raw_permissions = {}

        if isinstance(raw_permissions, Mapping):
            raw_rule = raw_permissions.get(action, {})
            if isinstance(raw_rule, Mapping):
                raw_mode = raw_rule.get("mode", "")
                reason = raw_rule.get("reason", "")
                mode = _parse_permission_mode(raw_mode)
                if mode is not None:
                    return ToolPermissionRule(
                        mode=mode,
                        reason=reason if isinstance(reason, str) else "",
                    )

        default_rule = DEFAULT_TOOL_PERMISSIONS.get(action)
        if default_rule is not None:
            return default_rule
        return ToolPermissionRule(PermissionMode.DENY, "未知高危行为，底座自动阻断")

    def _record_decision(
        self,
        action: str,
        resource: str,
        allowed: bool,
        mode: str,
        reason: str,
    ) -> None:
        get_runtime_observer().record_permission_decision(
            PermissionDecisionObservation(
                action=action,
                resource=resource,
                allowed=allowed,
                mode=mode,
                reason=reason,
            )
        )


def _has_path_escape(file_path: str) -> bool:
    return bool(file_path) and (
        ".." in file_path or "/" in file_path or "\\" in file_path
    )


def _parse_permission_mode(raw_mode: Any) -> PermissionMode | None:
    if not isinstance(raw_mode, str):
        return None
    try:
        return PermissionMode(raw_mode)
    except ValueError:
        return None
