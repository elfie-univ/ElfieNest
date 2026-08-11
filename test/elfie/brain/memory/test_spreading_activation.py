"""SpreadingActivation 扩散激活单元测试"""

import pytest

from elfie.brain.memory.node_types import EdgeTypes, MemoryNode
from elfie.brain.memory.spreading_activation import SpreadingActivation
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


@pytest.fixture
def storage():
    """提供内存数据库的 GraphStorage 实例"""
    gs = SQLiteMemoryStoreAdapter.in_memory()
    yield gs
    gs.close()


@pytest.fixture
def sa(storage):
    """提供 SpreadingActivation 实例"""
    return SpreadingActivation(storage)


def test_spread_single_seed(sa, storage):
    """单个种子节点扩散"""
    storage.add_node(MemoryNode(id="a", type="entity", content="A"))
    storage.add_node(MemoryNode(id="b", type="entity", content="B"))
    storage.add_edge("a", "b", EdgeTypes.INVOLVES, weight=1.0)

    result = sa.spread(["a"])

    assert "a" in result
    assert result["a"] == 1.0
    assert "b" in result
    # b: 种子1.0 × decay0.5 × weight1.0 = 0.5
    assert result["b"] == 1.0 * 0.5 * 1.0


def test_spread_multiple_seeds(sa, storage):
    """多个种子节点扩散"""
    storage.add_node(MemoryNode(id="a", type="entity", content="A"))
    storage.add_node(MemoryNode(id="b", type="entity", content="B"))
    storage.add_node(MemoryNode(id="c", type="entity", content="C"))
    storage.add_edge("a", "c", EdgeTypes.INVOLVES, weight=1.0)
    storage.add_edge("b", "c", EdgeTypes.INVOLVES, weight=1.0)

    result = sa.spread(["a", "b"])

    assert result["a"] == 1.0
    assert result["b"] == 1.0
    assert "c" in result
    # c 从 a 或 b 最先到达，visited-set 保证只激活一次
    assert result["c"] == 0.5


def test_spread_max_hops(sa, storage):
    """2跳限制"""
    storage.add_node(MemoryNode(id="a", type="entity", content="A"))
    storage.add_node(MemoryNode(id="b", type="entity", content="B"))
    storage.add_node(MemoryNode(id="c", type="entity", content="C"))
    storage.add_node(MemoryNode(id="d", type="entity", content="D"))
    storage.add_edge("a", "b", EdgeTypes.INVOLVES, weight=1.0)
    storage.add_edge("b", "c", EdgeTypes.INVOLVES, weight=1.0)
    storage.add_edge("c", "d", EdgeTypes.INVOLVES, weight=1.0)

    result = sa.spread(["a"], max_hops=2)

    assert "a" in result
    assert "b" in result  # 1跳
    assert "c" in result  # 2跳
    assert "d" not in result  # 3跳，超出max_hops限制


def test_spread_decay(sa, storage):
    """衰减系数生效"""
    storage.add_node(MemoryNode(id="a", type="entity", content="A"))
    storage.add_node(MemoryNode(id="b", type="entity", content="B"))
    storage.add_node(MemoryNode(id="c", type="entity", content="C"))
    storage.add_edge("a", "b", EdgeTypes.INVOLVES, weight=1.0)
    storage.add_edge("b", "c", EdgeTypes.INVOLVES, weight=1.0)

    # threshold=0 保证c（0.09）不被过滤，只验证衰减
    result = sa.spread(["a"], decay=0.3, threshold=0.0)

    # b: 1.0 * 0.3 * 1.0 = 0.3
    assert result["b"] == pytest.approx(0.3)
    # c: 0.3 * 0.3 * 1.0 = 0.09
    assert result["c"] == pytest.approx(0.09)


def test_spread_threshold(sa, storage):
    """低于阈值的节点被过滤"""
    storage.add_node(MemoryNode(id="a", type="entity", content="A"))
    storage.add_node(MemoryNode(id="b", type="entity", content="B"))
    storage.add_node(MemoryNode(id="c", type="entity", content="C"))
    storage.add_edge("a", "b", EdgeTypes.INVOLVES, weight=0.3)
    storage.add_edge("b", "c", EdgeTypes.INVOLVES, weight=0.3)

    # decay=1.0, threshold=0.5
    # b: 1.0 * 1.0 * 0.3 = 0.3 < 0.5 → 被过滤
    result = sa.spread(["a"], decay=1.0, threshold=0.5)

    assert "a" in result
    assert result["a"] == 1.0
    assert "b" not in result


def test_spread_visited_set(sa, storage):
    """防止循环（A→B→A不会无限循环）"""
    storage.add_node(MemoryNode(id="a", type="entity", content="A"))
    storage.add_node(MemoryNode(id="b", type="entity", content="B"))
    storage.add_edge("a", "b", EdgeTypes.INVOLVES, weight=1.0)
    storage.add_edge("b", "a", EdgeTypes.INVOLVES, weight=1.0)

    result = sa.spread(["a"], max_hops=5)

    assert "a" in result
    assert "b" in result
    # visited-set 阻止循环，a 和 b 各只出现一次
    assert len(result) == 2


def test_spread_no_edges(sa, storage):
    """无边的种子节点只返回自身"""
    storage.add_node(MemoryNode(id="a", type="entity", content="A"))

    result = sa.spread(["a"])

    assert result == {"a": 1.0}


def test_spread_edge_weight(sa, storage):
    """边权重影响激活值"""
    storage.add_node(MemoryNode(id="a", type="entity", content="A"))
    storage.add_node(MemoryNode(id="b", type="entity", content="B"))
    storage.add_node(MemoryNode(id="c", type="entity", content="C"))
    storage.add_edge("a", "b", EdgeTypes.INVOLVES, weight=0.8)
    storage.add_edge("a", "c", EdgeTypes.INVOLVES, weight=0.2)

    result = sa.spread(["a"])

    # b: 1.0 * 0.5 * 0.8 = 0.4
    assert result["b"] == pytest.approx(0.4)
    # c: 1.0 * 0.5 * 0.2 = 0.1
    assert result["c"] == pytest.approx(0.1)
