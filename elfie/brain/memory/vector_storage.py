import json
import logging
import math
import os
from typing import Any, Dict, List

logger = logging.getLogger("elfie.brain.memory.vector_storage")


class TinyVectorStorage:
    """中层：海马体 (轻量级纯 Python 向量/关键词语义记忆索引数据库)"""

    def __init__(self, storage_path: str = None):
        if storage_path is None:
            # 默认保存在当前工程根目录的 .elfie_memories.json 文件中
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 向上寻找到根目录
            self.storage_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(current_dir))),
                ".elfie_memories.json",
            )
        else:
            self.storage_path = storage_path

        self.memories: List[Dict[str, Any]] = []
        self._load_from_disk()

    def _load_from_disk(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, encoding="utf-8") as f:
                    self.memories = json.load(f)
                # 向后兼容：为旧记录补默认字段
                for entry in self.memories:
                    meta = entry.get("metadata")
                    if meta is None:
                        meta = {}
                        entry["metadata"] = meta
                    if "level" not in meta:
                        meta["level"] = "episodic"
                    if "intensity" not in meta:
                        meta["intensity"] = 0.0
                logger.info(
                    f"💾 [记忆读取完毕] 成功加载 {len(self.memories)} 条历史情景索引。"
                )
            except Exception as e:
                logger.error(f"加载记忆文件异常: {e}")
                self.memories = []
        else:
            logger.info("💾 初始化全新的海马体记忆存储。")
            self.memories = []

    def save_to_disk(self):
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.memories, f, ensure_ascii=False, indent=2)
            logger.info("💾 [记忆保存成功] 海马体记忆已安全落盘持久化。")
        except Exception as e:
            logger.error(f"保存记忆文件异常: {e}")

    def add_memory(self, text: str, tags: Dict[str, Any] = None, level: str = "episodic", intensity: float = 0.0):
        """
        向海马体存入一条新记忆
        :param text: 记忆陈述句
        :param tags: 记忆的辅助元数据（如 time, emotion_tag, location 等）
        :param level: 记忆层级（episodic/consolidated）
        :param intensity: 记忆强度 (0-100)
        """
        from datetime import datetime

        meta_tags = tags or {}
        if "timestamp" not in meta_tags:
            meta_tags["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta_tags["level"] = level
        meta_tags["intensity"] = intensity

        entry = {"content": text, "metadata": meta_tags}
        self.memories.append(entry)

        if len(self.memories) > 100:
            logger.warning(f"海马体记忆容量超过100条({len(self.memories)}条)，建议触发夜间巩固。")
            self.memories = self.memories[-100:]

        self.save_to_disk()

    def retrieve_relevant_memories(self, query: str, top_k: int = 2, current_emotion: str = None, level: str = None) -> List[str]:
        """
        检索语义最相关的 k 条记忆 (采用高效率的 TF-IDF 关键词语义相似打分，模拟向量距离)
        :param query: 检索 Prompt 或句子
        :param top_k: 获取多少条相关记忆
        :param current_emotion: 当前情绪（用于情绪加权）
        :param level: 记忆层级过滤
        :return: 相关的记忆文本列表
        """
        if not self.memories or not query:
            return []

        # 1. 简单的分词处理 (剥离标点，按空格或中文字符分词)
        query_words = self._tokenize(query)
        if not query_words:
            return [m["content"] for m in self.memories[:top_k]]

        # 先根据 level 过滤（如果有指定）
        candidate_memories = self.memories
        if level:
            candidate_memories = [m for m in self.memories if m.get("metadata", {}).get("level") == level]
            if not candidate_memories:
                return []

        scored_memories = []

        for entry in candidate_memories:
            content = entry["content"]
            content_words = self._tokenize(content)

            # 计算余弦相似度 / 词频交集
            intersection = set(query_words) & set(content_words)
            if not intersection:
                score = 0.0
            else:
                # 包含度计算
                score = len(intersection) / (
                    math.sqrt(len(query_words)) * math.sqrt(len(content_words))
                )

            # 情绪加权
            meta = entry.get("metadata") or {}
            if current_emotion is None:
                if meta.get("emotion") == "happy":
                    score *= 1.2
            else:
                if meta.get("emotion") == current_emotion:
                    intensity = meta.get("intensity", 0.0)
                    score *= 1.0 + (intensity / 100.0) * 0.5

            # consolidated 级别额外权重
            if meta.get("level") == "consolidated":
                score *= 1.3

            scored_memories.append((entry, score))

        # 按得分从高到低排序，过滤得分为 0.0 的记忆
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        results = [item[0]["content"] for item in scored_memories if item[1] > 0.0]

        # 如果相似度没有满足要求的，兜底返回最近的两条记忆
        if not results:
            results = [m["content"] for m in candidate_memories[-top_k:]]

        return results[:top_k]

    def _tokenize(self, text: str) -> List[str]:
        """对中文和英文混合句子进行简易提取关键词分词"""
        import re

        # 去掉非字符，只留下汉字、英文和数字
        cleaned = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", "", text)
        # 把中文字符拆开，英文字符按空格切分
        words = []
        for part in cleaned.split():
            # 判断是否包含汉字
            if re.search(r"[\u4e00-\u9fa5]", part):
                # 中文字符逐字拆解作为简单词袋
                words.extend(list(part))
            else:
                words.append(part.lower())
        return [w for w in words if len(w) > 0]
