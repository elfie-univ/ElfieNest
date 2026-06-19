import logging
from typing import Any, Dict

from elfie.brain.brain_types import BrainContext, SensorData

logger = logging.getLogger("elfie.brain.context_builder")


class ThalamusContextBuilder:
    """中层：丘脑 (上下文拼装总线 - Context Bus)"""

    def __init__(self):
        """初始化丘脑上下文拼装总线"""
        pass

    def assemble(
        self,
        raw_sensors: Dict[str, Any],
        energy_system: Any,
        emotion_engine: Any,
        memory_system: Any,
    ) -> BrainContext:
        """
        拉取多方状态，进行相关性拼接与噪点剥离，形成大脑皮层消费的 BrainContext
        :param raw_sensors: 底层爬行动物脑感觉器官捕获的瞬时裸数据
        :param energy_system: 下丘脑能量作息系统实例
        :param emotion_engine: 杏仁核情绪引擎实例
        :param memory_system: 海马体记忆检索实例
        :return: 精密组合的 BrainContext
        """
        logger.info(
            "丘脑十字路口：正在捕获外部感官、情感化学值、体能作息与海马体记忆切片..."
        )

        # 1. 过滤背景噪音（噪点剥离由 interface/signal_filter.py 或丘脑自身轻量策略完成）
        # 这里简单保留必要的感官通道信息
        sensor_data = SensorData(
            temperature=raw_sensors.get("temperature", 24.0),
            is_network_online=raw_sensors.get("is_network_online", True),
            salience_score=raw_sensors.get("salience_score", 0.0),
            has_new_message=raw_sensors.get("has_new_message", False),
            user_message=raw_sensors.get("user_message", ""),
        )

        # 2. 获取实时生理能耗参数与作息状态
        energy_level = energy_system.get_energy()
        fatigue_level = energy_system.get_fatigue()
        is_sleeping = energy_system.is_sleeping

        # 3. 抓取实时心情和情感状态标签
        realtime_emotion = emotion_engine.get_current_emotion_summary()
        dominant_mood = emotion_engine.get_dominant_mood()
        emotion_intensity = getattr(
            emotion_engine, "get_emotion_value", lambda _: 0.0
        )(dominant_mood)

        # 4. 使用记忆系统门面检索并组装5区域上下文
        user_message = sensor_data.user_message
        active_memory = memory_system
        if user_message and active_memory:
            memory_slices = active_memory.get_context(
                query=user_message,
                emotion=dominant_mood,
                intensity=emotion_intensity,
            )
        else:
            memory_slices = "无相关历史情景记忆。"

        # 5. 拼装 BrainContext 投递给大脑皮层
        assembled_context = BrainContext(
            sensors=sensor_data,
            energy=energy_level,
            fatigue=fatigue_level,
            is_sleeping=is_sleeping,
            emotion_state=realtime_emotion,
            emotion_mood=dominant_mood,
            emotion_intensity=emotion_intensity,
            history_episodes=memory_slices,
        )

        logger.info("丘脑拼装完成，已投递至 Neocortex 大脑皮层。")
        return assembled_context
