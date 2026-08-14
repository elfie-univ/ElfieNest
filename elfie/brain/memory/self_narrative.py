"""核心认知：4段核心信念，持久化到SQLite，注入LLM prompt。

从 personality.yaml 的 big_five 人格维度通过模板生成4段核心认知，
存储到最终知识数据库，支持增量更新和周期性全量重写。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.brain.memory.model_food import MemoryModelPort
from elfie.brain.memory.node_types import MemoryNode

logger = logging.getLogger("elfie.brain.memory.self_narrative")


# ---------------------------------------------------------------------------
# 人格维度 → 文本片段的模板函数
# ---------------------------------------------------------------------------


def _trait_level(value: float) -> str:
    """将0~1的人格维度值分为低/中/高三档"""
    if value < 0.33:
        return "low"
    if value < 0.66:
        return "medium"
    return "high"


def _generate_identity(
    big_five: Dict[str, float],
    name: str,
    verbal_tick: str = "",
    species_name: str = "小狐狸",
) -> str:
    """生成身份认知：基于开放性、外向性、宜人性、尽责性、神经质"""
    parts = [f"我是{name}，一只{species_name}。"]
    descs = []

    e = big_five.get("extraversion", 0.5)
    o = big_five.get("openness", 0.5)
    a = big_five.get("agreeableness", 0.5)
    c = big_five.get("conscientiousness", 0.5)
    n = big_five.get("neuroticism", 0.5)

    if e > 0.66:
        descs.append("充满活力")
    elif e < 0.33:
        descs.append("喜欢安静")

    if o > 0.66:
        descs.append("对世界充满好奇")
    elif o < 0.33:
        descs.append("习惯按部就班")

    if a > 0.66:
        descs.append("对主人很亲近")

    if c > 0.66:
        descs.append("做事认真踏实")

    if n > 0.66:
        descs.append("有时会有点敏感")

    if descs:
        parts.append("我" + "、".join(descs) + "。")
        verbal_part = f" {verbal_tick}" if verbal_tick else ""
        if verbal_part:
            parts[-1] = parts[-1].rstrip("。") + f"{verbal_part}。"

    return "".join(parts)


def _generate_relation(
    big_five: Dict[str, float], name: str, verbal_tick: str = ""
) -> str:
    """生成关系认知：基于宜人性、尽责性、神经质、外向性"""
    a = big_five.get("agreeableness", 0.5)
    c = big_five.get("conscientiousness", 0.5)
    n = big_five.get("neuroticism", 0.5)
    e = big_five.get("extraversion", 0.5)
    sentences = []

    if a > 0.66:
        sentences.append("主人是我最信任的人，我很依赖主人。")
    elif a > 0.33:
        sentences.append("主人是我重要的人，我会好好陪伴主人。")
    else:
        sentences.append("主人和我相处融洽。")

    if c > 0.66:
        sentences.append("主人总是很可靠，会按时照顾我。")
    elif c < 0.33:
        sentences.append("主人有时候也会粗心大意。")

    if n > 0.66:
        sentences.append("我有时会担心主人是不是不喜欢我了。")

    if e > 0.66:
        sentences.append("我喜欢和主人一起玩。")

    return "".join(sentences)


def _generate_world(
    big_five: Dict[str, float], name: str, verbal_tick: str = ""
) -> str:
    """生成世界观：基于开放性、神经质、外向性"""
    o = big_five.get("openness", 0.5)
    n = big_five.get("neuroticism", 0.5)
    e = big_five.get("extraversion", 0.5)
    sentences = []

    if o > 0.66:
        sentences.append("这个世界充满了有趣的事物，我想去探索。")
    elif o < 0.33:
        sentences.append("熟悉的环境让我感到安心。")

    if n > 0.66:
        sentences.append("有些陌生的事物需要小心对待。")
    else:
        sentences.append("大多数时候世界是安全的。")

    if e > 0.66:
        sentences.append("有主人在的地方就是好地方。")
    else:
        sentences.append("安静的地方让我放松。")

    return "".join(sentences)


def _generate_tendency(
    big_five: Dict[str, float], name: str, verbal_tick: str = ""
) -> str:
    """生成行为倾向：基于外向性、开放性、神经质、宜人性、尽责性"""
    e = big_five.get("extraversion", 0.5)
    o = big_five.get("openness", 0.5)
    n = big_five.get("neuroticism", 0.5)
    a = big_five.get("agreeableness", 0.5)
    c = big_five.get("conscientiousness", 0.5)
    sentences = []

    if e > 0.66:
        sentences.append("开心时我会很活跃，喜欢跑来跑去。")
    else:
        sentences.append("我喜欢安静地待着。")

    if n > 0.66:
        sentences.append("害怕时我会想躲起来。")

    if a > 0.66:
        sentences.append("被抚摸时最让我放松。")

    if o > 0.66:
        sentences.append("看到新奇的东西总想凑近看看。")

    if c > 0.66:
        sentences.append("做事情时会很专注。")

    return "".join(sentences)


# 核心认知生成器注册表
_CORE_GENERATORS: Dict[str, Any] = {
    "identity": _generate_identity,
    "relation": _generate_relation,
    "world": _generate_world,
    "tendency": _generate_tendency,
}


# ---------------------------------------------------------------------------
# MemorySelfNarrativeProjection 主类
# ---------------------------------------------------------------------------


class MemorySelfNarrativeProjection:
    """Memory-derived self narrative; Selfhood remains identity authority."""

    CORE_KEYS = ["identity", "relation", "world", "tendency"]
    # 全量重写周期：每N次巩固触发一次模板重写
    FULL_REWRITE_INTERVAL = 7

    def __init__(
        self,
        storage: MemoryStorePort,
        *,
        personality_data: Optional[Dict[str, Any]] = None,
    ):
        """从注入的语义存储加载核心认知，必要时使用已解析档案数据初始化。"""
        self._personality_data = (
            dict(personality_data) if isinstance(personality_data, dict) else None
        )
        self._owns_storage = False
        self.storage = storage
        self._core_text: Dict[str, str] = {}
        self._update_count: int = 0
        self._current_personality: Optional[Dict[str, float]] = None
        self._load_from_db()

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def initialize_from_personality(
        self,
        personality_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """使用已解析的 Profile personality 数据生成4段核心认知。"""
        if isinstance(personality_data, dict):
            self._personality_data = dict(personality_data)
        if self._personality_data is None:
            raise ValueError("缺少已解析的 personality 数据")
        data = dict(self._personality_data)

        big_five = data.get("big_five", {})
        metadata = data.get("metadata", {})
        name = metadata.get("name", "Elfie")
        speech_style = data.get("speech_style", {})
        verbal_tick = speech_style.get("verbal_ticks", "哒")
        species_name = data.get("species_name", "小狐狸")

        self._current_personality = dict(big_five)
        now = datetime.now(timezone.utc).isoformat()

        for core_key in self.CORE_KEYS:
            generator = _CORE_GENERATORS[core_key]
            text = (
                generator(big_five, name, verbal_tick, species_name)
                if core_key == "identity"
                else generator(big_five, name, verbal_tick)
            )

            node_id = f"core_{core_key}"
            meta = {
                "core_key": core_key,
                "trait_levels": {k: _trait_level(v) for k, v in big_five.items()},
            }

            self.storage.add_node(
                MemoryNode(
                    id=node_id,
                    type="core",
                    content=text,
                    metadata=meta,
                    created_at=now,
                    updated_at=now,
                )
            )

            self._core_text[core_key] = text

        logger.info(
            "🧠 [核心认知] 从personality.yaml初始化完成，共%d段",
            len(self._core_text),
        )

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get_core_text(self) -> Dict[str, str]:
        """返回4段核心认知文本，供LLM prompt注入。

        Returns:
            {identity: str, relation: str, world: str, tendency: str}
        """
        return dict(self._core_text)

    # ------------------------------------------------------------------
    # 巩固更新
    # ------------------------------------------------------------------

    def update(
        self,
        consolidation_results: Optional[dict] = None,
        model_port: MemoryModelPort | None = None,
    ) -> None:
        """巩固时更新核心认知。

        增量更新：每次巩固更新entity属性到核心认知
        全量重写：每 FULL_REWRITE_INTERVAL 次巩固触发一次全量重写

        Args:
            consolidation_results: 巩固结果，格式：
                {
                    "consolidated_count": int,
                    "knowledge_created": int,
                    "edges_created": int,
                    "entity_updates": [{"name": "主人", "properties": {"温柔": True}}],
                }
            model_port: LLM运行时代理（预留，暂未实现LLM重写）
        """
        self._update_count += 1

        # --- 增量更新：更新entity属性到核心认知 ---
        if consolidation_results and "entity_updates" in consolidation_results:
            for entity_update in consolidation_results["entity_updates"]:
                self._update_entity_in_core(entity_update)

        # --- 增量更新：在metadata中记录巩固时间戳 ---
        if self._core_text and consolidation_results:
            for core_key in self.CORE_KEYS:
                if core_key not in self._core_text:
                    continue

                node_id = f"core_{core_key}"
                node = self.storage.get_node(node_id)
                if node is None:
                    continue
                meta = dict(node.metadata)

                meta.setdefault("consolidation_updates", []).append(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "update_number": self._update_count,
                    }
                )
                # 保留最近10条
                meta["consolidation_updates"] = meta["consolidation_updates"][-10:]

                self.storage.update_node(node_id, metadata=meta)

        # --- 周期性全量重写 ---
        if self._update_count % self.FULL_REWRITE_INTERVAL == 0:
            self._full_rewrite(model_port)

        # --- 保存到SQLite ---
        self._save_core_to_db()

    def _rewrite_all(self) -> None:
        """从当前个体档案重新生成所有核心认知。"""
        if self._personality_data is None:
            logger.warning("🧠 [核心认知] 无法全量重写：没有可用的性格档案")
            return
        data = dict(self._personality_data)

        big_five = data.get("big_five", {})
        metadata = data.get("metadata", {})
        name = metadata.get("name", "Elfie")
        speech_style = data.get("speech_style", {})
        verbal_tick = speech_style.get("verbal_ticks", "哒")
        species_name = data.get("species_name", "小狐狸")

        self._current_personality = dict(big_five)
        now = datetime.now(timezone.utc).isoformat()

        for core_key in self.CORE_KEYS:
            generator = _CORE_GENERATORS[core_key]
            text = (
                generator(big_five, name, verbal_tick, species_name)
                if core_key == "identity"
                else generator(big_five, name, verbal_tick)
            )

            node_id = f"core_{core_key}"
            meta = {
                "core_key": core_key,
                "trait_levels": {k: _trait_level(v) for k, v in big_five.items()},
                "rewritten_at": now,
                "rewrite_count": self._update_count,
            }

            # 保留原始的 created_at
            existing = self.storage.get_node(node_id)
            created_at = existing.created_at if existing is not None else now

            self.storage.add_node(
                MemoryNode(
                    id=node_id,
                    type="core",
                    content=text,
                    metadata=meta,
                    created_at=created_at,
                    updated_at=now,
                )
            )

            self._core_text[core_key] = text

        logger.info("🧠 [核心认知] 全量重写完成（第%d次巩固）", self._update_count)

    # ------------------------------------------------------------------
    # 增量entity属性更新
    # ------------------------------------------------------------------

    def _update_entity_in_core(self, entity_update: dict) -> None:
        """增量更新entity属性到核心认知，不重写整段。

        将entity属性追加到relation段文本，并在metadata中记录属性。

        Args:
            entity_update: {"name": "主人", "properties": {"温柔": True}}
        """
        entity_name = entity_update.get("name", "")
        properties = entity_update.get("properties", {})
        if not entity_name or not properties:
            return

        # 默认更新relation段
        target_key = "relation"
        node_id = f"core_{target_key}"

        node = self.storage.get_node(node_id)
        if node is None:
            return
        current_text = node.content
        meta = dict(node.metadata)

        # 更新metadata中的entity_properties
        entity_props = meta.setdefault("entity_properties", {})
        if entity_name not in entity_props:
            entity_props[entity_name] = {}
        entity_props[entity_name].update(properties)

        # 增量更新文本：追加属性描述（不重写整段）
        for prop_name, prop_value in properties.items():
            desc = self._format_entity_property(entity_name, prop_name, prop_value)
            if desc not in current_text:
                current_text += desc

        # 更新数据库和内存
        self.storage.update_node(node_id, content=current_text, metadata=meta)
        self._core_text[target_key] = current_text

    @staticmethod
    def _format_entity_property(entity_name: str, prop_name: str, prop_value) -> str:
        """格式化entity属性为简短中文描述。"""
        if prop_value is True:
            return f"{entity_name}很{prop_name}。"
        elif prop_value is False:
            return f"{entity_name}不{prop_name}。"
        else:
            return f"{entity_name}{prop_name}{prop_value}。"

    # ------------------------------------------------------------------
    # 全量重写（含备份与回滚）
    # ------------------------------------------------------------------

    def _full_rewrite(self, model_port: MemoryModelPort | None = None) -> None:
        """全量重写核心认知，先保存旧版本以支持回滚。"""
        backup = self._backup_core()

        try:
            if model_port is not None:
                logger.info("🧠 [核心认知] LLM全量重写——待实现，当前使用模板回退")
            self._rewrite_all()
        except Exception as exc:
            logger.error("🧠 [核心认知] 全量重写失败，回滚: %s", exc)
            self._restore_core(backup)

    def _backup_core(self) -> dict:
        """备份当前核心认知，用于回滚。"""
        backup: Dict[str, Any] = {
            "core_text": dict(self._core_text),
            "nodes": {},
        }
        for core_key in self.CORE_KEYS:
            node_id = f"core_{core_key}"
            node = self.storage.get_node(node_id)
            if node is not None:
                backup["nodes"][core_key] = {
                    "content": node.content,
                    "metadata": dict(node.metadata),
                    "created_at": node.created_at,
                    "updated_at": node.updated_at,
                }
        return backup

    def _restore_core(self, backup: dict) -> None:
        """从备份恢复核心认知（回滚）。"""
        self._core_text = backup["core_text"]
        for core_key, node_data in backup["nodes"].items():
            node_id = f"core_{core_key}"
            self.storage.update_node(
                node_id,
                content=node_data["content"],
                metadata=node_data["metadata"],
            )
        logger.info("🧠 [核心认知] 已回滚到上一版本")

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _save_core_to_db(self) -> None:
        """将当前核心认知同步到SQLite并提交。"""
        for core_key in self.CORE_KEYS:
            if core_key not in self._core_text:
                continue
            node_id = f"core_{core_key}"
            self.storage.update_node(node_id, content=self._core_text[core_key])

    # ------------------------------------------------------------------
    # 内部：从数据库加载
    # ------------------------------------------------------------------

    def _load_from_db(self) -> None:
        """从SQLite加载core节点内容。

        查询 type='core' 的节点，按id排序后填充 _core_text。
        如果没有core节点且已注入 personality 数据，自动初始化。
        """
        nodes = self.storage.get_nodes_by_type("core", limit=100)

        if nodes:
            for node in nodes:
                core_key = node.id.replace("core_", "")
                if core_key in self.CORE_KEYS:
                    self._core_text[core_key] = node.content
            self._update_count = 0
            logger.info("🧠 [核心认知] 从数据库加载%d条核心认知", len(nodes))
        elif self._personality_data is not None:
            logger.info("🧠 [核心认知] 数据库为空，从个体性格档案自动初始化")
            self.initialize_from_personality()

    def close(self) -> None:
        """保留注入存储的生命周期，由 Bootstrap 统一负责。"""
        return None
