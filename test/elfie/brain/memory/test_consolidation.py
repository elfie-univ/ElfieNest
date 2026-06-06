"""巩固引擎单元测试

测试 MemoryConsolidator 的8步骤巩固流程：
1. 收集未巩固episodic
2. 按entity分组
3. 知识提炼（规则降级）
4. 创建knowledge节点
5. 建语义边
6. 因果边
7. 实体属性更新
8. 标记已巩固
"""

import pytest

from elfie.brain.memory.consolidation import MemoryConsolidator
from elfie.brain.memory.graph_storage import GraphStorage
from elfie.brain.memory.node_types import Edge, MemoryNode, NodeTypes, EdgeTypes


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _setup_basic_data(storage: GraphStorage):
    """设置基础测试数据：实体 + 未巩固的episodic（带involves边）"""
    # 实体
    ent_1 = MemoryNode(id="ent_1", type="entity", content="主人")
    ent_2 = MemoryNode(id="ent_2", type="entity", content="猫玩具")
    storage.add_node(ent_1)
    storage.add_node(ent_2)

    # 未巩固episodic（关联"主人"）
    for i in range(3):
        ep = MemoryNode(
            id=f"ep_{i}",
            type="episodic",
            content=f"和主人一起玩的第{i+1}次",
            metadata={"emotion": "happy", "timestamp": f"2026-06-0{i+1}T10:00:00"},
            edges=[Edge(target="ent_1", rel="involves", weight=0.7)],
        )
        storage.add_node(ep)

    # 未巩固episodic（关联"猫玩具"）
    for i in range(3, 5):
        ep = MemoryNode(
            id=f"ep_{i}",
            type="episodic",
            content=f"玩猫玩具追来追去第{i-2}次",
            metadata={"emotion": "excited", "timestamp": f"2026-06-0{i+1}T14:00:00"},
            edges=[Edge(target="ent_2", rel="involves", weight=0.6)],
        )
        storage.add_node(ep)

    # 单个未巩固episodic（无entity关联）
    ep_orphan = MemoryNode(
        id="ep_orphan",
        type="episodic",
        content="独自在窗边看风景",
        metadata={"emotion": "calm", "timestamp": "2026-06-05T16:00:00"},
    )
    storage.add_node(ep_orphan)

    # 已巩固episodic（不应被收集）
    ep_consolidated = MemoryNode(
        id="ep_consolidated",
        type="episodic",
        content="已巩固的旧记忆",
        metadata={"consolidated": True},
        edges=[Edge(target="ent_1", rel="involves", weight=0.5)],
    )
    storage.add_node(ep_consolidated)


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------

class TestMemoryConsolidator:
    """MemoryConsolidator 基础功能测试"""

    @pytest.fixture
    def storage(self):
        """创建内存SQLite存储"""
        gs = GraphStorage(db_path=":memory:")
        yield gs

    @pytest.fixture
    def consolidator(self, storage):
        """创建巩固器（无核心认知，简化测试）"""
        return MemoryConsolidator(storage=storage)

    # ------------------------------------------------------------------
    # 步骤1：收集未巩固节点
    # ------------------------------------------------------------------

    def test_collect_unconsolidated(self, storage, consolidator):
        """收集未巩固episodic节点，排除已巩固节点"""
        _setup_basic_data(storage)

        nodes = consolidator._collect_unconsolidated()
        node_ids = {n.id for n in nodes}

        # 未巩固的episodic节点应被收集
        assert "ep_0" in node_ids
        assert "ep_1" in node_ids
        assert "ep_2" in node_ids
        assert "ep_3" in node_ids
        assert "ep_4" in node_ids
        assert "ep_orphan" in node_ids
        # 已巩固的episodic节点应被排除
        assert "ep_consolidated" not in node_ids
        # 不应包含entity节点
        assert "ent_1" not in node_ids
        assert "ent_2" not in node_ids

    def test_collect_unconsolidated_all_done(self, storage, consolidator):
        """所有节点已巩固时返回空列表"""
        ep = MemoryNode(
            id="ep_done", type="episodic", content="done",
            metadata={"consolidated": True},
        )
        storage.add_node(ep)
        assert consolidator._collect_unconsolidated() == []

    # ------------------------------------------------------------------
    # 步骤2：按entity分组
    # ------------------------------------------------------------------

    def test_group_by_entity(self, storage, consolidator):
        """按entity分组：同一entity的episodic归入一组"""
        _setup_basic_data(storage)
        episodic_nodes = consolidator._collect_unconsolidated()

        groups = consolidator._group_by_entity(episodic_nodes)

        # 主组：关联"主人"的episodic
        assert "ent_1" in groups
        assert groups["ent_1"]["entity_node"] is not None
        assert groups["ent_1"]["entity_node"].content == "主人"
        ent_1_ids = {n.id for n in groups["ent_1"]["nodes"]}
        assert ent_1_ids == {"ep_0", "ep_1", "ep_2"}

        # 主组：关联"猫玩具"的episodic
        assert "ent_2" in groups
        assert groups["ent_2"]["entity_node"] is not None
        assert groups["ent_2"]["entity_node"].content == "猫玩具"
        ent_2_ids = {n.id for n in groups["ent_2"]["nodes"]}
        assert ent_2_ids == {"ep_3", "ep_4"}

        # 未分组：无entity关联的episodic
        assert "_ungrouped_" in groups
        orphan_ids = {n.id for n in groups["_ungrouped_"]["nodes"]}
        assert orphan_ids == {"ep_orphan"}

    def test_group_by_entity_empty(self, consolidator):
        """空列表返回空分组"""
        groups = consolidator._group_by_entity([])
        assert groups == {}

    # ------------------------------------------------------------------
    # 步骤3：规则提取（LLM降级）
    # ------------------------------------------------------------------

    def test_rule_based_extraction(self, consolidator):
        """规则提取：频率模式、情绪模式、去重"""
        group = [
            MemoryNode(
                id="e1", type="episodic", content="test1",
                metadata={"emotion": "happy"},
            ),
            MemoryNode(
                id="e2", type="episodic", content="test2",
                metadata={"emotion": "happy"},
            ),
            MemoryNode(
                id="e3", type="episodic", content="test3",
                metadata={"emotion": "happy"},
            ),
        ]

        items = consolidator._rule_based_extraction(group, "测试实体")

        # 频率模式（>=3次）
        freq_items = [i for i in items if i["type"] == "pattern"]
        assert len(freq_items) >= 1
        assert "测试实体" in freq_items[0]["content"]
        assert "3次" in freq_items[0]["content"]

        # 情绪模式（所有记录情绪一致）
        emotion_items = [i for i in items if "总是感到" in i["content"]]
        assert len(emotion_items) == 1
        assert "happy" in emotion_items[0]["content"]

        # 去重
        contents = [i["content"] for i in items]
        assert len(contents) == len(set(contents))

    def test_rule_based_extraction_empty_group(self, consolidator):
        """空组返回空列表"""
        assert consolidator._rule_based_extraction([], "test") == []

    def test_rule_based_extraction_no_emotion(self, consolidator):
        """无情绪元数据时只提取频率模式"""
        group = [
            MemoryNode(id="e1", type="episodic", content="test1"),
            MemoryNode(id="e2", type="episodic", content="test2"),
            MemoryNode(id="e3", type="episodic", content="test3"),
        ]
        items = consolidator._rule_based_extraction(group, "实体A")
        # 应该有1个频率模式
        assert len(items) == 1
        assert items[0]["type"] == "pattern"
        assert "实体A" in items[0]["content"]

    # ------------------------------------------------------------------
    # 步骤4：创建knowledge节点
    # ------------------------------------------------------------------

    def test_create_knowledge_nodes(self, storage, consolidator):
        """创建knowledge节点，包含正确的类型、内容和源引用"""
        knowledge_items = [
            {"content": "主人喜欢摸艾菲的头", "type": "knowledge", "confidence": 0.9},
            {"content": "每次被摸头都会开心", "type": "pattern", "confidence": 0.8},
        ]
        source_ids = ["ep_0", "ep_1"]

        knowledge_ids = consolidator._create_knowledge_nodes(
            knowledge_items, source_ids,
        )

        assert len(knowledge_ids) == 2

        # 验证节点已创建
        for kid in knowledge_ids:
            node = storage.get_node(kid)
            assert node is not None
            assert node.type == NodeTypes.KNOWLEDGE.value
            assert node.metadata.get("source_ids") == source_ids
            assert node.metadata.get("created_in_consolidation") is True

        # 验证具体内容
        node_0 = storage.get_node(knowledge_ids[0])
        assert node_0.content == "主人喜欢摸艾菲的头"

        node_1 = storage.get_node(knowledge_ids[1])
        assert node_1.content == "每次被摸头都会开心"

    def test_create_knowledge_nodes_empty(self, consolidator):
        """空知识项创建空列表"""
        ids = consolidator._create_knowledge_nodes([], ["ep_0"])
        assert ids == []

    # ------------------------------------------------------------------
    # 步骤5：语义边
    # ------------------------------------------------------------------

    def test_build_semantic_edges(self, storage, consolidator):
        """建语义边：supports（knowledge→episodic）和 about（knowledge→entity）"""
        # 准备前置节点
        for nid in ["k_1", "k_2", "ep_src_1", "ep_src_2", "ent_target"]:
            storage.add_node(MemoryNode(
                id=nid, type="episodic" if nid.startswith("ep") else "entity",
                content=nid,
            ))

        knowledge_ids = ["k_1", "k_2"]
        source_ids = ["ep_src_1", "ep_src_2"]
        entity_ids = ["ent_target"]

        edge_count = consolidator._build_semantic_edges(
            knowledge_ids, source_ids, entity_ids,
        )

        # 2 knowledge × 2 source × 1 supports + 2 knowledge × 1 entity × 1 about = 6
        assert edge_count == 6

        # 验证supports边
        for kid in knowledge_ids:
            outgoing = storage.get_edges(kid, direction="outgoing")
            rels = {e.rel for e in outgoing}
            assert EdgeTypes.SUPPORTS.value in rels
            assert EdgeTypes.ABOUT.value in rels

            # supports指向原始episodic
            supports_targets = {
                e.target for e in outgoing
                if e.rel == EdgeTypes.SUPPORTS.value
            }
            assert supports_targets == set(source_ids)

            # about指向entity
            about_targets = {
                e.target for e in outgoing
                if e.rel == EdgeTypes.ABOUT.value
            }
            assert about_targets == set(entity_ids)

    def test_build_semantic_edges_no_entity(self, storage, consolidator):
        """无entity时只创建supports边"""
        storage.add_node(MemoryNode(id="k_1", type="knowledge", content="test"))
        storage.add_node(MemoryNode(id="ep_src", type="episodic", content="src"))

        edge_count = consolidator._build_semantic_edges(
            ["k_1"], ["ep_src"], [],
        )
        assert edge_count == 1

        outgoing = storage.get_edges("k_1", direction="outgoing")
        assert len(outgoing) == 1
        assert outgoing[0].rel == EdgeTypes.SUPPORTS.value
        assert outgoing[0].target == "ep_src"

    # ------------------------------------------------------------------
    # 步骤8：标记已巩固
    # ------------------------------------------------------------------

    def test_mark_consolidated(self, storage, consolidator):
        """标记episodic节点为consolidated=True"""
        for i in range(3):
            storage.add_node(MemoryNode(
                id=f"ep_{i}", type="episodic", content=f"test{i}",
            ))

        consolidator._mark_consolidated(["ep_0", "ep_1", "ep_2"])

        for i in range(3):
            node = storage.get_node(f"ep_{i}")
            assert node.metadata.get("consolidated") is True
            assert "consolidated_at" in node.metadata

    def test_mark_consolidated_deduplicates(self, storage, consolidator):
        """重复ID不会导致重复更新"""
        storage.add_node(MemoryNode(id="ep_1", type="episodic", content="test"))

        consolidator._mark_consolidated(["ep_1", "ep_1", "ep_1"])

        node = storage.get_node("ep_1")
        assert node.metadata.get("consolidated") is True

    # ------------------------------------------------------------------
    # 完整巩固流程（无LLM）
    # ------------------------------------------------------------------

    def test_run_consolidation_full(self, storage, consolidator):
        """完整巩固流程（无LLM，使用规则提取降级）"""
        _setup_basic_data(storage)

        result = consolidator.run_consolidation(runtime_agent=None)

        # 验证结果
        assert result["consolidated_count"] == 6  # ep_0~4 + ep_orphan
        assert result["knowledge_created"] > 0
        assert result["edges_created"] > 0

        # 验证episodic节点已标记consolidated
        for i in range(5):
            node = storage.get_node(f"ep_{i}")
            assert node.metadata.get("consolidated") is True
        node = storage.get_node("ep_orphan")
        assert node.metadata.get("consolidated") is True

        # 已巩固的节点不受影响
        node = storage.get_node("ep_consolidated")
        assert node.metadata.get("consolidated") is True

        # 验证knowledge节点已创建
        knowledge_nodes = storage.get_nodes_by_type("knowledge")
        assert len(knowledge_nodes) > 0
        for kn in knowledge_nodes:
            assert kn.metadata.get("created_in_consolidation") is True

        # 验证语义边已创建
        knowledge_ids = [kn.id for kn in knowledge_nodes]
        for kid in knowledge_ids:
            outgoing = storage.get_edges(kid, direction="outgoing")
            rels = {e.rel for e in outgoing}
            assert EdgeTypes.SUPPORTS.value in rels

        # 验证entity属性已更新
        ent_1 = storage.get_node("ent_1")
        assert ent_1.metadata.get("consolidationInteractions") == 3  # ep_0,1,2
        assert "consolidationEmotions" in ent_1.metadata
        assert ent_1.metadata["consolidationEmotions"].get("happy") == 3

        ent_2 = storage.get_node("ent_2")
        assert ent_2.metadata.get("consolidationInteractions") == 2  # ep_3,4
        assert ent_2.metadata["consolidationEmotions"].get("excited") == 2

        # 验证正确返回
        assert result["consolidated_count"] + result["knowledge_created"] + result["edges_created"] > 0

    def test_run_consolidation_empty(self, storage, consolidator):
        """无未巩固节点时返回空结果"""
        # 只有已巩固节点
        storage.add_node(MemoryNode(
            id="ep_done", type="episodic", content="done",
            metadata={"consolidated": True},
        ))

        result = consolidator.run_consolidation()

        assert result["consolidated_count"] == 0
        assert result["knowledge_created"] == 0
        assert result["edges_created"] == 0

    def test_run_consolidation_empty_storage(self, storage, consolidator):
        """空存储返回空结果"""
        result = consolidator.run_consolidation()
        assert result["consolidated_count"] == 0
        assert result["knowledge_created"] == 0
        assert result["edges_created"] == 0

    # ------------------------------------------------------------------
    # 安全性：LLM失败时保留原始数据
    # ------------------------------------------------------------------

    def test_consolidation_safety(self, storage, consolidator):
        """LLM失败时保留原始数据，降级为规则提取"""
        _setup_basic_data(storage)

        # 模拟一个会抛异常的runtime_agent
        class FailingAgent:
            @staticmethod
            def ask(prompt, **kwargs):
                raise RuntimeError("LLM故障")

            def __call__(self, *args, **kwargs):
                raise RuntimeError("LLM故障")

        failing_agent = FailingAgent()

        # 运行巩固（LLM会失败，应降级为规则提取）
        result = consolidator.run_consolidation(runtime_agent=failing_agent)

        # 巩固仍应完成（使用规则提取降级）
        assert result["consolidated_count"] > 0

        # 原始episodic节点仍然存在
        for i in range(5):
            node = storage.get_node(f"ep_{i}")
            assert node is not None
            assert node.content  # 内容未被清空

        # knowledge节点被创建（规则提取的产物）
        knowledge_nodes = storage.get_nodes_by_type("knowledge")
        assert len(knowledge_nodes) > 0

        # 原始节点未被物理删除
        assert storage.count_nodes("episodic") >= 6  # 6个episodic还在

    def test_consolidation_safety_no_llm(self, storage, consolidator):
        """无LLM时不阻塞巩固，静默降级"""
        _setup_basic_data(storage)

        # 不传入runtime_agent
        result = consolidator.run_consolidation()

        # 巩固应正常完成
        assert result["consolidated_count"] > 0
        assert result["knowledge_created"] > 0
        assert result["edges_created"] > 0

        # 数据完整
        for i in range(5):
            assert storage.get_node(f"ep_{i}") is not None
        assert storage.get_node("ent_1") is not None
        assert storage.get_node("ent_2") is not None

    # ------------------------------------------------------------------
    # 安全性：增量操作，不物理删除
    # ------------------------------------------------------------------

    def test_no_physical_deletion(self, storage, consolidator):
        """巩固不物理删除任何节点"""
        _setup_basic_data(storage)

        before_count = storage.count_nodes()
        consolidator.run_consolidation()
        after_count = storage.count_nodes()

        # 节点总数增加（新增knowledge节点）
        assert after_count > before_count

        # 所有原始节点仍然存在
        for nid in ["ep_0", "ep_1", "ep_2", "ep_3", "ep_4", "ep_orphan",
                     "ep_consolidated", "ent_1", "ent_2"]:
            assert storage.get_node(nid) is not None

    # ------------------------------------------------------------------
    # 重复巩固安全性
    # ------------------------------------------------------------------

    def test_idempotent_consolidation(self, storage, consolidator):
        """已巩固节点再次运行巩固时不重复处理"""
        _setup_basic_data(storage)

        # 第一次巩固
        result1 = consolidator.run_consolidation()
        assert result1["consolidated_count"] == 6

        # 第二次巩固（所有节点已巩固）
        result2 = consolidator.run_consolidation()
        assert result2["consolidated_count"] == 0
        assert result2["knowledge_created"] == 0
