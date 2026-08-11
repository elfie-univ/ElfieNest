"""测试核心认知初始化和持久化。

测试覆盖：
- 从 personality.yaml 初始化4段核心认知
- get_core_text 格式验证
- 总 Token 数量约束
- 增量更新与周期全量重写
- 注入的语义存储生命周期
"""

from elfie.brain.memory.core_cognition import CoreCognition
from elfie.profile import load_packaged_profile_defaults
from test.elfie.brain.memory.fake_store import FakeMemoryStore

# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------

_PERSONALITY_DATA = load_packaged_profile_defaults()["personality"]


def _make_cc() -> CoreCognition:
    """创建一个不依赖技术持久化的 CoreCognition 测试实例。"""
    return CoreCognition(
        storage=FakeMemoryStore.in_memory(),
        personality_data=_PERSONALITY_DATA,
    )


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


class TestCoreCognition:
    """核心认知初始化与持久化测试"""

    def test_initialize_from_personality(self):
        """从yaml初始化，4段核心认知全部生成"""
        cc = CoreCognition(
            storage=FakeMemoryStore.in_memory(),
            personality_data=None,
        )
        # 初始状态：无核心认知
        assert len(cc._core_text) == 0
        assert cc.get_core_text() == {}

        # 从yaml初始化
        cc.initialize_from_personality(_PERSONALITY_DATA)

        core_text = cc.get_core_text()
        assert len(core_text) == 4
        for key in CoreCognition.CORE_KEYS:
            assert key in core_text
            # 每段至少包含一个有意义的句子
            assert len(core_text[key]) >= 10, (
                f"{key} 段内容过短: {len(core_text[key])} 字符"
            )

        # 数据库中也应有记录
        assert cc.storage.count_nodes("core") == 4

    def test_get_core_text_format(self):
        """返回dict包含identity/relation/world/tendency"""
        cc = _make_cc()
        result = cc.get_core_text()

        assert isinstance(result, dict)
        assert set(result.keys()) == {"identity", "relation", "world", "tendency"}
        assert all(isinstance(v, str) for v in result.values())

        # 返回的是副本，修改不影响内部状态
        original = dict(result)
        result["extra"] = "injected"
        assert "extra" not in cc.get_core_text()
        assert cc.get_core_text() == original

    def test_core_text_token_limit(self):
        """总文本≤800 tokens（约400英文词）"""
        cc = _make_cc()
        core_text = cc.get_core_text()

        total_chars = sum(len(v) for v in core_text.values())
        # 中文字符：800 tokens ≈ 1200~1600 字符，用2000字符作为安全上限
        assert total_chars <= 2000, (
            f"核心认知总字符数 {total_chars} 超过2000（≈800 tokens）"
        )

        # 每段至少10个字符
        for key, text in core_text.items():
            assert len(text) >= 10, f"{key} 段长度不足: {len(text)} 字符"

        # 打印总统计以供调试
        char_counts = {k: len(v) for k, v in core_text.items()}
        print(f"  [字符统计] {char_counts} | 总计: {total_chars}")

    def test_storage_lifecycle_is_owned_by_the_injected_port(self):
        """Brain only writes semantic nodes; Bootstrap owns persistence reopen."""
        cc = _make_cc()
        assert cc.storage.count_nodes("core") == 4
        cc.storage.close()

    def test_update_incremental(self):
        """增量更新核心认知（metadata）"""
        cc = _make_cc()
        original_text = dict(cc._core_text)
        assert cc._update_count == 0

        # 第一次增量更新
        cc.update(consolidation_results={"emotion": "happy", "intensity": 0.8})

        assert cc._update_count == 1
        # 核心文本内容不应变化
        assert cc.get_core_text() == original_text

        # metadata 应包含 consolidation_updates 记录
        node = cc.storage.get_node("core_identity")
        assert node is not None
        meta = node.metadata
        assert "consolidation_updates" in meta
        assert len(meta["consolidation_updates"]) == 1
        assert "update_number" in meta["consolidation_updates"][0]

        # 第二次增量更新
        cc.update(consolidation_results={"emotion": "sad"})
        assert cc._update_count == 2

        node = cc.storage.get_node("core_identity")
        assert node is not None
        meta = node.metadata
        assert len(meta["consolidation_updates"]) == 2

    def test_update_triggers_rewrite(self):
        """每 FULL_REWRITE_INTERVAL 次 update 触发全量重写"""
        cc = _make_cc()

        # 执行 FULL_REWRITE_INTERVAL 次 update
        for i in range(CoreCognition.FULL_REWRITE_INTERVAL):
            cc.update(consolidation_results={"tick": i})

        assert cc._update_count == CoreCognition.FULL_REWRITE_INTERVAL

        # 全量重写后，metadata 应包含 rewritten_at
        node = cc.storage.get_node("core_identity")
        assert node is not None
        meta = node.metadata
        assert "rewritten_at" in meta, (
            f"第{CoreCognition.FULL_REWRITE_INTERVAL}次update应触发全量重写"
        )
        assert meta.get("rewrite_count") == CoreCognition.FULL_REWRITE_INTERVAL

        # 所有core节点都应包含 rewrite 标记
        for node in cc.storage.get_nodes_by_type("core"):
            meta = node.metadata
            assert "rewritten_at" in meta, f"节点 {node.id} 缺少 rewritten_at"

    def test_update_entity_properties(self):
        """增量更新entity属性到核心认知"""
        cc = _make_cc()
        original_text = dict(cc.get_core_text())

        # 更新entity属性
        cc.update(
            consolidation_results={
                "entity_updates": [
                    {"name": "主人", "properties": {"温柔": True}},
                ],
            }
        )

        # relation段文本应包含属性描述
        relation_text = cc.get_core_text()["relation"]
        assert "主人很温柔" in relation_text, (
            f"relation段应包含'主人很温柔'，实际: {relation_text}"
        )

        # 其他段文本不应变化
        for key in ["identity", "world", "tendency"]:
            assert cc.get_core_text()[key] == original_text[key], f"{key}段不应变化"

        # metadata应包含entity_properties
        node = cc.storage.get_node("core_relation")
        assert node is not None
        meta = node.metadata
        assert "entity_properties" in meta
        assert "主人" in meta["entity_properties"]
        assert meta["entity_properties"]["主人"]["温柔"] is True

    def test_update_full_rewrite(self):
        """每7次巩固触发全量重写，metadata包含rewritten_at"""
        cc = _make_cc()

        # 执行6次update（不触发全量重写）
        for i in range(6):
            cc.update(consolidation_results={"tick": i})

        assert cc._update_count == 6

        # 第7次update应触发全量重写
        cc.update(consolidation_results={"tick": 6})
        assert cc._update_count == 7

        # 全量重写后，metadata应包含rewritten_at
        node = cc.storage.get_node("core_identity")
        assert node is not None
        meta = node.metadata
        assert "rewritten_at" in meta, f"第7次update应触发全量重写，metadata: {meta}"
        assert meta.get("rewrite_count") == 7

        # 所有core节点都应包含rewrite标记
        for node in cc.storage.get_nodes_by_type("core"):
            meta = node.metadata
            assert "rewritten_at" in meta, f"节点 {node.id} 缺少 rewritten_at"

    def test_update_rollback(self):
        """全量重写失败时回滚到旧版本"""
        cc = _make_cc()

        # 先做一次entity更新，使核心认知有变化
        cc.update(
            consolidation_results={
                "entity_updates": [
                    {"name": "主人", "properties": {"温柔": True}},
                ],
            }
        )
        assert "主人很温柔" in cc.get_core_text()["relation"]

        # 执行5次普通update
        for i in range(5):
            cc.update(consolidation_results={"tick": i})

        # 记录重写前的核心认知文本
        text_before_rewrite = dict(cc._core_text)

        # 模拟_rewrite_all抛出异常
        from unittest import mock

        with mock.patch.object(
            cc, "_rewrite_all", side_effect=RuntimeError("模拟重写失败")
        ):
            # 第7次update触发全量重写并失败
            cc.update(consolidation_results={"tick": 6})

        # 回滚后，核心认知应恢复到重写前的状态
        assert cc._update_count == 7
        for key in CoreCognition.CORE_KEYS:
            assert cc._core_text[key] == text_before_rewrite[key], (
                f"回滚后{key}段应与重写前一致"
            )

        # entity属性应保留（回滚到重写前状态，包含entity更新）
        assert "主人很温柔" in cc._core_text["relation"]
