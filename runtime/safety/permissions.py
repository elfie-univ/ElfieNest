import logging
import os

logger = logging.getLogger("runtime.safety.permissions")


class PermissionDeniedError(Exception):
    """大模型进行越权或高危敏感操作被底层物理防御阻断的异常"""

    pass


class PermissionManager:
    """策略性自动审计管理器，守护精灵自进化的物理边界"""

    def __init__(self, config):
        self.config = config
        # 定义夜间 N3 整理专用的系统高特权令牌
        # 可以从环境变量获取，或者在启动时随机生成一个以确保本地安全
        self._admin_token = os.getenv(
            "ELFIE_ADMIN_TOKEN", "elfie_sleep_evolution_token_2026"
        )

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
        logger.info(f"🛡️ 权限安全审计中... 行为: {action}, 资源: {file_path}")

        # 1. 普通安全行为自动放行
        if action in ("READ", "RUN_SKILL"):
            return True

        # 2. 追加新技能 (Tool Synthesis 自进化) 自动放行
        if action == "CREATE_SKILL":
            # 强化审计：防止文件名注入攻击（如带有 ../ 等路径穿越）
            if file_path and (
                ".." in file_path or "/" in file_path or "\\" in file_path
            ):
                raise PermissionDeniedError(
                    f"❌ 路径审计拦截！不允许跨越自定义技能根目录：'{file_path}'"
                )
            return True

        # 3. 敏感的删除/优化重写 (清理冗余) 必须校验特权令牌
        if action == "DELETE_SKILL":
            if token == self._admin_token:
                logger.info("🔑 [特权令牌校验通过] 允许执行离线技能库代谢与去重操作")
                return True
            else:
                reason = "日常运行中，大模型无权删除或覆盖已有的稳定技能脚本！"
                logger.error(f"❌ 越权拦截：{reason}")
                raise PermissionDeniedError(
                    f"❌ 越权执行被物理阻断！原因：{reason}\n"
                    f"💡 技能代谢只允许在精灵 N3 深度睡眠模式下，由高特权整理模型（携带 admin_token）执行。"
                )

        raise PermissionDeniedError(f"❌ 未知高危行为 '{action}'，底座自动阻断。")
