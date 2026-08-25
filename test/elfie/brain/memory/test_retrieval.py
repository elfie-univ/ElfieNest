"""多维检索引擎单元测试

测试 MemoryRetriever 的5个检索入口及合并去重逻辑。
"""

from datetime import datetime, timedelta

import pytest

from elfie.brain.memory.node_types import (
    EdgeTypes,
    MemoryNode,
    NodeTypes,
    RetrievalQuery,
)
from elfie.brain.memory.retrieval import MemoryRetriever
from elfie.brain.memory.sensory_index import SensoryIndexer
from test.elfie.brain.memory.fake_store import FakeMemoryStore


def _seed_test_data(gs: FakeMemoryStore):
    """填充测试数据：5个episodic节点 + 3个entity节点 + 边 + 感官索引"""
    now = datetime.now()

    episodes = [
        MemoryNode(
            id="ep_1",
            type=NodeTypes.EPISODIC.value,
            content="今天在公园里看到一只红色的鸟",
            metadata={
                "emotion": "好奇",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
            },
        ),
        MemoryNode(
            id="ep_2",
            type=NodeTypes.EPISODIC.value,
            content="在森林里遇到一只鹿",
            metadata={
                "emotion": "惊喜",
                "timestamp": (now - timedelta(hours=3)).isoformat(),
            },
        ),
        MemoryNode(
            id="ep_3",
            type=NodeTypes.EPISODIC.value,
            content="朋友送了一束花，很开心",
            metadata={
                "emotion": "开心",
                "timestamp": (now - timedelta(hours=5)).isoformat(),
            },
        ),
        MemoryNode(
            id="ep_4",
            type=NodeTypes.EPISODIC.value,
            content="下雨天在家里看书",
            metadata={
                "emotion": "平静",
                "timestamp": (now - timedelta(hours=12)).isoformat(),
            },
        ),
        MemoryNode(
            id="ep_5",
            type=NodeTypes.EPISODIC.value,
            content="做了一个奇怪的梦",
            metadata={
                "emotion": "好奇",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
            },
        ),
    ]
    for ep in episodes:
        gs.add_node(ep)

    # 创建entity节点，内容就是实体名称
    entities = [
        MemoryNode(id="ent_1", type=NodeTypes.ENTITY.value, content="公园"),
        MemoryNode(id="ent_2", type=NodeTypes.ENTITY.value, content="森林"),
        MemoryNode(id="ent_3", type=NodeTypes.ENTITY.value, content="鸟"),
    ]
    for ent in entities:
        gs.add_node(ent)

    # 编码权威方向：episodic → involves → entity
    gs.add_edge("ep_1", "ent_1", EdgeTypes.INVOLVES.value, 0.9)
    gs.add_edge("ep_2", "ent_2", EdgeTypes.INVOLVES.value, 0.85)
    gs.add_edge("ep_1", "ent_3", EdgeTypes.INVOLVES.value, 0.8)

    # 添加感官索引数据
    sensory_data = [
        ("红色", "visual", "ep_1", 0.9),
        ("鸟叫声", "auditory", "ep_1", 0.7),
        ("鹿", "visual", "ep_2", 0.85),
        ("花香", "olfactory", "ep_3", 0.75),
    ]
    indexer = SensoryIndexer(gs)
    for sense_key, sense_type, node_id, _weight in sensory_data:
        indexer.index_sensory(node_id, {sense_type: sense_key})


class TestMemoryRetriever:
    """测试多维检索引擎的每个检索入口"""

    @pytest.fixture
    def storage(self):
        gs = FakeMemoryStore.in_memory()
        _seed_test_data(gs)
        yield gs
        gs.close()

    @pytest.fixture
    def retriever(self, storage):
        return MemoryRetriever(storage)

    # ──────────── 文字检索 ────────────

    def test_retrieve_by_text(self, retriever):
        """文字检索：按关键词搜索内容匹配的记忆"""
        results = retriever.retrieve_by_text("公园", top_k=5)
        ids = [n.id for n in results]
        assert "ep_1" in ids, "ep_1内容包含'公园'，应该被检索到"

    def test_retrieve_by_text_includes_recallable_knowledge(self, storage, retriever):
        storage.add_node(
            MemoryNode(
                id="knowledge-elfaria",
                type=NodeTypes.KNOWLEDGE.value,
                content="我来自 Elfaria。",
                metadata={
                    "recall_eligible": True,
                    "source_event_ids": ["genesis:fact:elfie-1:0"],
                },
            )
        )

        results = retriever.retrieve_by_text("Elfaria", top_k=5)

        assert "knowledge-elfaria" in [node.id for node in results]

    def test_retrieve_by_text_only_returns_episodic_memories(self, retriever):
        """公开文字检索不暴露内部实体、知识或核心认知节点。"""
        # Given: "公园"同时命中一个情景节点和内部实体节点。

        # When
        results = retriever.retrieve_by_text("公园", top_k=5)

        # Then
        assert results
        assert {node.type for node in results} == {NodeTypes.EPISODIC.value}

    def test_retrieve_by_text_no_match(self, retriever):
        """文字检索：无匹配返回空列表"""
        results = retriever.retrieve_by_text("人工智能量子计算", top_k=5)
        assert results == []

    # ──────────── 实体检索 ────────────

    def test_retrieve_by_entity(self, retriever):
        """实体检索：通过entity节点和INVOLVES边找到关联的episodic"""
        results = retriever.retrieve_by_entity(["公园"], top_k=5)
        ids = [n.id for n in results]
        assert "ep_1" in ids, "公园通过INVOLVES边关联到ep_1"
        assert len(results) >= 1

    def test_retrieve_by_entity_multiple(self, retriever):
        """实体检索：多实体查询返回结果合并"""
        results = retriever.retrieve_by_entity(["公园", "鸟"], top_k=5)
        ids = [n.id for n in results]
        assert "ep_1" in ids, "公园和鸟都关联到ep_1"
        # 去重后只有一个
        assert len(ids) == 1

    def test_retrieve_by_entity_no_match(self, retriever):
        """实体检索：不存在的实体返回空"""
        results = retriever.retrieve_by_entity(["火星"], top_k=5)
        assert results == []

    # ──────────── 情绪检索 ────────────

    def test_retrieve_by_emotion(self, retriever):
        """情绪检索：查找同情绪的episodic记忆"""
        results = retriever.retrieve_by_emotion("好奇", top_k=5)
        ids = [n.id for n in results]
        assert "ep_1" in ids
        assert "ep_5" in ids
        assert len(results) >= 2

    def test_retrieve_by_emotion_no_match(self, retriever):
        """情绪检索：无匹配情绪返回空"""
        results = retriever.retrieve_by_emotion("愤怒", top_k=5)
        assert results == []

    # ──────────── 时间检索 ────────────

    def test_retrieve_by_time(self, retriever):
        """时间检索：查找时间相近的episodic记忆"""
        # 查询时间为2小时前，ep_5（2小时前）和ep_1（1小时前）应该最接近
        query_time = (datetime.now() - timedelta(hours=2)).isoformat()
        results = retriever.retrieve_by_time(query_time, top_k=5)
        ids = [n.id for n in results]
        # ep_5 正好在查询时间点，ep_1 差1小时
        assert "ep_5" in ids, "ep_5时间匹配"
        assert "ep_1" in ids, "ep_1时间相近"

        # ep_5应该排第一（时间完全相同）
        assert results[0].id == "ep_5"

    def test_retrieve_by_time_far_past(self, retriever):
        """时间检索：超过24小时的记忆不返回"""
        query_time = (datetime.now() - timedelta(days=2)).isoformat()
        results = retriever.retrieve_by_time(query_time, top_k=5)
        assert results == []

    def test_retrieve_by_time_invalid(self, retriever):
        """时间检索：无效时间字符串返回空"""
        results = retriever.retrieve_by_time("not-a-date", top_k=5)
        assert results == []

    # ──────────── 感官检索 ────────────

    def test_retrieve_by_sensory(self, retriever):
        """感官检索：通过节点语义元数据查找感官匹配的记忆"""
        results = retriever.retrieve_by_sensory({"visual": "红色"}, top_k=5)
        ids = [n.id for n in results]
        assert "ep_1" in ids, "红色在感官索引中关联到ep_1"

    def test_retrieve_by_sensory_no_match(self, retriever):
        """感官检索：无匹配感官返回空"""
        results = retriever.retrieve_by_sensory({"auditory": "雷声"}, top_k=5)
        assert results == []

    # ──────────── 综合检索 ────────────

    def test_retrieve_comprehensive(self, retriever):
        """综合检索：多维度合并去重"""
        query = RetrievalQuery(
            text_query="鸟",
            current_emotion="好奇",
            current_entities=["公园"],
            current_time=datetime.now().isoformat(),
            current_sensory={"visual": "红色"},
        )
        results = retriever.retrieve(query, top_k=10)
        ids = [n.id for n in results]
        # ep_1 在5个维度中至少匹配了4个（文字+情绪+实体+感官），应该排在首位
        assert "ep_1" in ids, "ep_1在多维度下被检索到"
        assert "ep_5" in ids, "ep_5通过情绪'好奇'被检索到"
        # ep_1 得分应该最高（多维度匹配）
        assert results[0].id == "ep_1"

    def test_retrieve_comprehensive_deduplicate(self, retriever):
        """综合检索：同一节点在多个维度匹配，去重后只出现一次"""
        query = RetrievalQuery(
            text_query="鸟",
            current_emotion="好奇",
            current_entities=["公园"],
        )
        results = retriever.retrieve(query, top_k=10)
        ids = [n.id for n in results]
        # ep_1在文字/情绪/实体三个维度都匹配，但去重后只出现一次
        assert ids.count("ep_1") == 1

    # ──────────── 空查询 ────────────

    def test_retrieve_empty_query(self, retriever):
        """空查询：所有字段为空时返回空列表"""
        query = RetrievalQuery()
        results = retriever.retrieve(query, top_k=10)
        assert results == []

    # ──────────── 合并去重 ────────────

    def test_merge_and_deduplicate(self, retriever):
        """合并去重：得分累加，去重，top_k截断"""
        # 构造3个有重叠的结果列表
        node_a = MemoryNode(id="a", type="episodic", content="记忆A")
        node_a.metadata["_retrieval_score"] = 0.8
        node_b = MemoryNode(id="b", type="episodic", content="记忆B")
        node_b.metadata["_retrieval_score"] = 0.6
        node_c = MemoryNode(id="c", type="episodic", content="记忆C")
        node_c.metadata["_retrieval_score"] = 0.4

        # 先将节点存入storage以供merge重新查询
        for n in [node_a, node_b, node_c]:
            retriever.storage.add_node(n)

        list1 = [node_a, node_b]
        list2 = [node_b, node_c]
        list3 = [node_a, node_c]

        merged = retriever._merge_and_deduplicate([list1, list2, list3], top_k=2)
        ids = [n.id for n in merged]

        # a: 0.8+0.8=1.6（出现在list1和list3）
        # b: 0.6+0.6=1.2（出现在list1和list2）
        # c: 0.4+0.4=0.8（出现在list2和list3）
        assert len(merged) == 2, "top_k=2应返回2个"
        assert merged[0].id == "a", "a得分最高应排第一"
        assert "a" in ids
        assert "b" in ids
        assert "c" not in ids, "c得分最低被截断"
