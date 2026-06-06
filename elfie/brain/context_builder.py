import logging
from typing import Any, Dict

logger = logging.getLogger("elfie.brain.context_builder")


class ThalamusContextBuilder:
    """中层：丘脑 (上下文拼装总线 - Context Bus)"""

    def __init__(self):
        pass

    def assemble(
        self,
        raw_sensors: Dict[str, Any],
        energy_system: Any,
        emotion_engine: Any,
        memory_system: Any,
    ) -> Dict[str, Any]:
        """
        拉取多方状态，进行相关性拼接与噪点剥离，形成大脑皮层消费的 Context 字典
        :param raw_sensors: 底层爬行动物脑感觉器官捕获的瞬时裸数据
        :param energy_system: 下丘脑能量作息系统实例
        :param emotion_engine: 杏仁核情绪引擎实例
        :param memory_system: 海马体记忆检索实例
        :return: 精密组合的 Context 字典
        """
        logger.info(
            "丘脑十字路口：正在捕获外部感官、情感化学值、体能作息与海马体记忆切片..."
        )

        # 1. 过滤背景噪音（噪点剥离由 interface/signal_filter.py 或丘脑自身轻量策略完成）
        # 这里简单保留必要的感官通道信息
        filtered_sensors = {
            "temperature": raw_sensors.get("temperature", 24.0),
            "is_network_online": raw_sensors.get("is_network_online", True),
            "salience_score": raw_sensors.get("salience_score", 0.0),
            "has_new_message": raw_sensors.get("has_new_message", False),
            "user_message": raw_sensors.get("user_message", ""),
        }

        # 2. 获取实时生理能耗参数与作息状态
        energy_level = energy_system.get_energy()
        fatigue_level = energy_system.get_fatigue()
        is_sleeping = energy_system.is_sleeping

        # 3. 抓取实时心情和情感状态标签
        realtime_emotion = emotion_engine.get_current_emotion_summary()
        dominant_mood = emotion_engine.get_dominant_mood()

        # 4. 检索海马体中的相关记忆片段 (根据主人发送的话进行关键词或向量索引)
        user_message = filtered_sensors["user_message"]
        memory_slices = "无相关历史情景记忆。"
        if user_message and memory_system:
            retrieved = memory_system.retrieve_relevant_memories(
                user_message,
                current_emotion=dominant_mood,
            )
            if retrieved:
                memory_slices = "\n".join(f"- {m}" for m in retrieved)

        # 5. 拼装总线包投递给大脑皮层
        assembled_context = {
            "sensors": filtered_sensors,
            "energy": energy_level,
            "fatigue": fatigue_level,
            "is_sleeping": is_sleeping,
            "emotion_state": realtime_emotion,
            "emotion_mood": dominant_mood,
            "history_episodes": memory_slices,
        }

        logger.info("丘脑拼装完成，已投递至 Neocortex 大脑皮层。")
        return assembled_context
