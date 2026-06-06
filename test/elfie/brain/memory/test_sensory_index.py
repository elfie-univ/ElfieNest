"""感官索引单元测试

测试 SensoryIndexer 的索引建立、检索、获取和删除功能。
"""

import pytest

from elfie.brain.memory.graph_storage import GraphStorage
from elfie.brain.memory.node_types import MemoryNode
from elfie.brain.memory.sensory_index import SensoryIndexer


class TestSensoryIndexer:
    """测试 SensoryIndexer 的核心功能"""

    @pytest.fixture
    def storage(self):
        """创建内存 SQLite GraphStorage 实例"""
        gs = GraphStorage(db_path=":memory:")
        yield gs

    @pytest.fixture
    def indexer(self, storage):
        """创建 SensoryIndexer 实例"""
        return SensoryIndexer(storage)

    @pytest.fixture
    def sample_node(self, storage):
        """创建一个示例节点用于索引测试"""
        node = MemoryNode(
            id="sensory_test_node_001",
            type="episodic",
            content="用户端来一碗热腾腾的鱼汤，温暖灯光下轻声交谈。",
        )
        storage.add_node(node)
        return node

    def test_index_sensory(self, indexer, sample_node):
        """为节点建立感官索引"""
        sensory = {
            "olfactory": "鱼味",
            "visual": "温暖色调",
            "auditory": "温柔语调",
            "tactile": "温热食物",
        }
        indexer.index_sensory(sample_node.id, sensory)

        # 验证数据已写入 sensory_index 表
        cursor = indexer.storage.conn.execute(
            "SELECT COUNT(*) FROM sensory_index WHERE node_id=?",
            (sample_node.id,),
        )
        assert cursor.fetchone()[0] == 4

        # 验证每种感官类型都正确存储
        for sense_type, sense_key in sensory.items():
            cursor = indexer.storage.conn.execute(
                "SELECT sense_key, sense_type FROM sensory_index WHERE node_id=? AND sense_type=?",
                (sample_node.id, sense_type),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row["sense_key"] == sense_key
            assert row["sense_type"] == sense_type

    def test_search_by_sensory(self, indexer, sample_node):
        """按感官类型和关键词检索节点"""
        # 建立索引并检索
        sensory = {"olfactory": "鱼味", "visual": "温暖色调"}
        indexer.index_sensory(sample_node.id, sensory)

        results = indexer.search_by_sensory("olfactory", "鱼味", top_k=5)
        assert len(results) == 1
        assert results[0][0] == sample_node.id
        assert results[0][1] == 0.8

        results = indexer.search_by_sensory("visual", "色调", top_k=5)
        assert len(results) == 1
        assert results[0][0] == sample_node.id

    def test_search_by_sensory_no_match(self, indexer, sample_node):
        """无匹配时返回空列表"""
        indexer.index_sensory(sample_node.id, {"olfactory": "鱼味"})

        results = indexer.search_by_sensory("olfactory", "花香", top_k=5)
        assert results == []

        results = indexer.search_by_sensory("visual", "红色", top_k=5)
        assert results == []

    def test_get_sensory_for_node(self, indexer, sample_node):
        """获取节点的所有感官索引"""
        sensory = {
            "olfactory": "鱼味",
            "visual": "温暖色调",
            "auditory": "温柔语调",
            "tactile": "温热食物",
        }
        indexer.index_sensory(sample_node.id, sensory)

        result = indexer.get_sensory_for_node(sample_node.id)
        assert result["olfactory"] == ["鱼味"]
        assert result["visual"] == ["温暖色调"]
        assert result["auditory"] == ["温柔语调"]
        assert result["tactile"] == ["温热食物"]

    def test_get_sensory_for_node_no_index(self, indexer):
        """未建立索引的节点返回空字典"""
        result = indexer.get_sensory_for_node("nonexistent_node")
        assert result == {}

    def test_remove_sensory_index(self, indexer, sample_node):
        """删除节点的感官索引"""
        sensory = {"olfactory": "鱼味", "visual": "温暖色调"}
        indexer.index_sensory(sample_node.id, sensory)

        # 确认索引已存在
        cursor = indexer.storage.conn.execute(
            "SELECT COUNT(*) FROM sensory_index WHERE node_id=?",
            (sample_node.id,),
        )
        assert cursor.fetchone()[0] == 2

        # 删除索引后验证已清空
        indexer.remove_sensory_index(sample_node.id)
        cursor = indexer.storage.conn.execute(
            "SELECT COUNT(*) FROM sensory_index WHERE node_id=?",
            (sample_node.id,),
        )
        assert cursor.fetchone()[0] == 0

    def test_index_multiple_sensory(self, indexer, sample_node):
        """一个节点多个感官类型"""
        sensory = {
            "olfactory": "鱼味",
            "visual": "温暖色调",
            "auditory": "温柔语调",
            "tactile": "温热食物",
        }
        indexer.index_sensory(sample_node.id, sensory)

        # 验证所有感官类型都已索引
        for sense_type in ["olfactory", "visual", "auditory", "tactile"]:
            cursor = indexer.storage.conn.execute(
                "SELECT sense_key FROM sensory_index WHERE node_id=? AND sense_type=?",
                (sample_node.id, sense_type),
            )
            row = cursor.fetchone()
            assert row is not None, f"缺少感官类型: {sense_type}"

    def test_index_sensory_upsert(self, indexer, sample_node):
        """重复索引同一感官类型应覆盖而非重复"""
        indexer.index_sensory(sample_node.id, {"olfactory": "鱼味"})
        indexer.index_sensory(sample_node.id, {"olfactory": "鱼味"})

        cursor = indexer.storage.conn.execute(
            "SELECT COUNT(*) FROM sensory_index WHERE node_id=? AND sense_type='olfactory'",
            (sample_node.id,),
        )
        assert cursor.fetchone()[0] == 1

    def test_search_by_sensory_multiple_nodes(self, indexer, storage):
        """多个节点具有相同感官关键词的检索"""
        node1 = MemoryNode(id="multi_sense_001", type="episodic", content="鱼汤很鲜美")
        node2 = MemoryNode(id="multi_sense_002", type="episodic", content="煎鱼的味道")
        storage.add_node(node1)
        storage.add_node(node2)

        indexer.index_sensory(node1.id, {"olfactory": "鱼味"})
        indexer.index_sensory(node2.id, {"olfactory": "鱼味"})

        results = indexer.search_by_sensory("olfactory", "鱼味", top_k=5)
        assert len(results) == 2
        assert results[0][1] == 0.8
        assert results[1][1] == 0.8
