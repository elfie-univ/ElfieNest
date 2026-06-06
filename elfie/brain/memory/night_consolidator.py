import logging
from collections import Counter

from elfie.brain.memory.episode_manager import EpisodeMemoryManager

logger = logging.getLogger("elfie.brain.memory.night_consolidator")


class NightMemoryConsolidator:
    """中层：海马体夜间整理系统 (睡时记忆压缩与长期记忆固化 Worker)"""

    def __init__(self, episode_manager: EpisodeMemoryManager):
        self.mgr = episode_manager

    def run_consolidation(self, runtime_agent) -> str:
        """
        运行夜间整理 (当且仅当精灵在下丘脑指示休眠状态下被唤起)
        使用大模型底座进行离线压缩流水账

        :param runtime_agent: 需要 ask(prompt, energy, task_complexity) 方法的对象
        :return: 固化之后的长期特征字符串
        """
        all_episodes = self.mgr.get_all_episodes()
        if len(all_episodes) < 3:
            logger.info("海马体空闲：白天的流水经历记录过少，无需触发离线整理。")
            return "No consolidation needed."

        logger.info(
            f"😴 [海马体夜间离线固化中...] 正在打包压缩 {len(all_episodes)} 条流水经历记录..."
        )

        # 提取主导情绪和最大强度
        dominant_emotion = self._get_dominant_emotion(all_episodes)
        max_intensity = self._get_max_intensity(all_episodes)

        # 1. 抽提所有的白天流水账
        raw_events = [
            f"- [{e['metadata'].get('timestamp', '')}] {e['content']}"
            for e in all_episodes
        ]
        events_block = "\n".join(raw_events)

        # 2. 调用外挂算力底座，智能抽提长期设定与特征
        prompt = (
            "你是一个长期记忆固化系统。\n"
            "以下是精灵小狐狸艾菲今天发生的所有流水账事件列表：\n"
            f"{events_block}\n\n"
            "请将以上流水事件进行深度分析与压缩，提取出最核心的 2 条长期概括记忆（例如：‘主人关心艾菲并帮艾菲充了电’，或是‘主人算过一笔 1250 元的账单’）。\n"
            "只返回这 2 条高度浓缩的情景陈述句，每行一条，去掉冗余的时间戳和标点符号。"
        )

        # 安全调用 LLM：先捕获异常，不修改任何记忆
        try:
            condensed = runtime_agent.ask(prompt, energy=100.0, task_complexity=3)
        except Exception as e:
            logger.error(f"夜间记忆固化失败: {e}，将在下一个休眠周期重试。")
            return f"Error during consolidation: {e}"

        # LLM 返回空结果时不修改任何记忆
        if not condensed or not condensed.strip():
            logger.warning("LLM返回空结果，保留原记忆")
            return "No consolidation produced."

        logger.info(f"🧠 [海马体固化成功] 提取到的长期核心特征如下:\n{condensed}")

        # 3. 安全固化：先写入巩固后的新记忆，再清除原始流水记忆
        for line in condensed.splitlines():
            if line.strip():
                cleaned_line = line.strip().lstrip("-* ").strip()
                self.mgr.storage.add_memory(
                    text=f"【长期固化记忆】 {cleaned_line}",
                    tags={"emotion": dominant_emotion},
                    level="consolidated",
                    intensity=max_intensity,
                )

        # 清除原始流水记忆（仅保留已固化的新记忆）
        self.mgr.storage.memories = [
            m
            for m in self.mgr.storage.memories
            if m.get("metadata", {}).get("level") == "consolidated"
        ]
        self.mgr.storage.save_to_disk()
        return condensed

    @staticmethod
    def _get_dominant_emotion(episodes):
        """从 episodes 中提取最频繁的情绪标签"""
        emotions = [e.get("metadata", {}).get("emotion", "calm") for e in episodes]
        counter = Counter(emotions)
        return counter.most_common(1)[0][0]

    @staticmethod
    def _get_max_intensity(episodes):
        """从 episodes 中提取最大 intensity"""
        intensities = [e.get("metadata", {}).get("intensity", 0.0) for e in episodes]
        return max(intensities) if intensities else 0.0
