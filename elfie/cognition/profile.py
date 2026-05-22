import os
import yaml
import logging
from typing import Dict, Any, List

logger = logging.getLogger("elfie.cognition.profile")

class ElfieProfile:
    """精灵性格与载体物理设定的管理模块 (自我认知系统)"""

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            # 默认路径设为当前文件所在目录的上一级 config 文件夹
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.config_dir = os.path.join(os.path.dirname(current_dir), "config")
        else:
            self.config_dir = config_dir

        self.personality = self._load_yaml("personality.yaml")
        self.capabilities = self._load_yaml("capabilities.yaml")
        self.system_limits = self._load_yaml("system_limits.yaml")

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        path = os.path.join(self.config_dir, filename)
        if not os.path.exists(path):
            logger.warning(f"配置文件未找到: {path}，将采用内存默认项。")
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"加载 {filename} 失败: {e}")
            return {}

    def get_system_prompt_segment(self) -> str:
        """为大模型生成系统 Prompt 设定中的性格和物理限制片段"""
        meta = self.personality.get("metadata", {})
        big_five = self.personality.get("big_five", {})
        speech = self.personality.get("speech_style", {})
        caps = self.capabilities.get("actuators", {})
        limits = self.capabilities.get("physics_limits", {})

        segment = (
            f"你的名字是：{meta.get('name', '艾菲')}\n"
            f"自我设定：{meta.get('description', '小精灵')}\n\n"
            f"【性格特征】 (大五人格得分 0-1)：\n"
            f"- 开放度 (Openness): {big_five.get('openness', 0.5)} (胡思乱想度)\n"
            f"- 尽责度 (Conscientiousness): {big_five.get('conscientiousness', 0.5)}\n"
            f"- 外向度 (Extraversion): {big_five.get('extraversion', 0.5)}\n"
            f"- 宜人性 (Agreeableness): {big_five.get('agreeableness', 0.5)}\n"
            f"- 情绪不稳定度 (Neuroticism): {big_five.get('neuroticism', 0.5)}\n\n"
            f"【物理躯体限制】 (你必须在行动前校验自己是否拥有相应能力)：\n"
            f"- 允许的躯体行动: {', '.join(caps.get('motion', {}).get('supported_actions', ['mutter']))}\n"
            f"- 飞行能力: {limits.get('can_fly', False)}\n"
            f"- 下水游泳能力: {limits.get('can_swim', False)}\n\n"
            f"【表达偏好】:\n"
            f"- 回复时要活泼生动，多体现出傲娇与可爱的属性。句尾口癖尽量带“{speech.get('verbal_ticks', '哒')}”。"
        )
        return segment

    def get_mutter_templates(self, mood: str) -> List[str]:
        """根据心情返回好玩的碎碎念模板列表"""
        speech = self.personality.get("speech_style", {})
        mutter_map = speech.get("mutter_templates", {})
        return mutter_map.get(mood, ["(艾菲摇了摇耳朵，陷入了深思...)"])
