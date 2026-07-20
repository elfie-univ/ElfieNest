"""大脑数据结构：边缘系统 ↔ 大脑皮层的数据契约

替代原来的裸 Dict[str, Any]，提供类型安全的数据交换结构。
这些结构是单次 tick 的内存数据包，不持久化。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SensorData:
    """底层感官数据（经过丘脑噪点剥离后）

    对应原来 context["sensors"] 子字典。
    来源：Elfie 从 raw_sensor_data 过滤后传入丘脑。
    """
    temperature: float = 24.0
    is_network_online: bool = True
    salience_score: float = 0.0
    has_new_message: bool = False
    user_message: str = ""
    images: tuple[str, ...] = ()
    audio: str | None = None


@dataclass
class BrainContext:
    """边缘系统 → 大脑皮层 的数据契约

    由丘脑（ThalamusContextBuilder.assemble()）从各边缘系统模块组装，
    投递给大脑皮层（NeocortexBrain.think_and_decide()）消费。

    一次 tick 的内存数据包，用完即丢，不持久化。
    """
    # 感官
    sensors: SensorData = field(default_factory=SensorData)
    # 生理（下丘脑）
    energy: float = 100.0
    fatigue: float = 0.0
    is_sleeping: bool = False
    # 情绪（杏仁核）
    emotion_state: str = "平静"       # 情绪摘要文本
    emotion_mood: str = "calm"        # 主导情绪标签
    emotion_intensity: float = 0.0    # 当前情绪强度 0-100
    # 记忆（海马体）
    history_episodes: str = "无相关历史情景记忆。"
    # 具身形态
    embodied_anatomy: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrainDecision:
    """大脑皮层 → 执行层 的决策契约

    由 NeocortexBrain.think_and_decide() 返回，
    Elfie.perceive_and_respond() 消费后驱动执行器。
    """
    action: str = "blink_eyes"
    speech_text: str = ""
    attention_mode: str = "DMN_IDLE"   # SN | CEN | DMN_ACTIVE | DMN_IDLE
    mutter: Optional[str] = None
