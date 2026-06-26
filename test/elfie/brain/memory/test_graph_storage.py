"""图谱存储单元测试

测试 GraphStorage 的 SQLite 初始化、表结构、索引和 WAL 模式。
"""

import os
import sqlite3
import tempfile

import pytest

from elfie.brain.memory.graph_storage import GraphStorage
from elfie.brain.memory.node_types import Edge, MemoryNode


class TestGraphStorage:
    """测试 GraphStorage 的初始化和模式创建"""

    @pytest.fixture
    def storage(self):
        """创建内存 SQLite GraphStorage 实例"""
        gs = GraphStorage(db_path=":memory:")
        yield gs

    def test_init_in_memory(self, storage):
        """验证内存数据库初始化成功"""
        assert storage is not None
        assert storage.conn is not None
        assert isinstance(storage.conn, sqlite3.Connection)

    def test_wal_mode_enabled(self, tmp_path):
        """验证 WAL 模式已启用（文件数据库）"""
        db_file = tmp_path / "test_wal.db"
        gs = GraphStorage(db_path=str(db_file))
        cursor = gs.conn.execute("PRAGMA journal_mode")
        row = cursor.fetchone()
        assert row is not None
        # WAL 模式返回 'wal'（小写）
        assert row[0].lower() == "wal"
        gs.close()

    def test_init_creates_parent_directory(self, tmp_path):
        db_file = tmp_path / "missing" / "test.db"

        gs = GraphStorage(db_path=str(db_file))

        assert db_file.exists()
        gs.close()

    def test_nodes_table_exists(self, storage):
        """验证 nodes 表存在且有正确字段"""
        cursor = storage.conn.execute("PRAGMA table_info(nodes)")
        columns = {row[1]: row for row in cursor.fetchall()}
        assert "id" in columns
        assert columns["id"][2] == "TEXT"  # 类型
        # id 是主键
        assert columns["id"][5] == 1  # pk flag

        assert "type" in columns
        assert columns["type"][2] == "TEXT"
        assert columns["type"][3] == "NOT NULL" or columns["type"][3] == 1

        assert "content" in columns
        assert columns["content"][2] == "TEXT"
        assert columns["content"][3] == "NOT NULL" or columns["content"][3] == 1

        assert "metadata" in columns
        assert columns["metadata"][2] == "TEXT"

        assert "edges" in columns
        assert columns["edges"][2] == "TEXT"

        assert "created_at" in columns
        assert "updated_at" in columns

        # 验证总字段数
        assert len(columns) == 7

    def test_nodes_table_default_values(self, storage):
        """验证 nodes 表字段默认值"""
        cursor = storage.conn.execute("PRAGMA table_info(nodes)")
        columns = {row[1]: row for row in cursor.fetchall()}
        # metadata 默认 '{}'
        assert columns["metadata"][4] == "'{}'" or columns["metadata"][4] == '{}'
        # edges 默认 '[]'
        assert columns["edges"][4] == "'[]'" or columns["edges"][4] == '[]'

    def test_edges_table_exists(self, storage):
        """验证 edges 表存在且有正确字段"""
        cursor = storage.conn.execute("PRAGMA table_info(edges)")
        columns = {row[1]: row for row in cursor.fetchall()}
        assert "id" in columns
        assert columns["id"][5] == 1  # pk

        assert "source_id" in columns
        assert columns["source_id"][2] == "TEXT"
        assert columns["source_id"][3] == "NOT NULL" or columns["source_id"][3] == 1

        assert "target_id" in columns
        assert columns["target_id"][2] == "TEXT"
        assert columns["target_id"][3] == "NOT NULL" or columns["target_id"][3] == 1

        assert "rel" in columns
        assert columns["rel"][2] == "TEXT"
        assert columns["rel"][3] == "NOT NULL" or columns["rel"][3] == 1

        assert "weight" in columns
        assert columns["weight"][2] == "REAL"

        # 验证总字段数
        assert len(columns) == 5

    def test_edges_table_default_weight(self, storage):
        """验证 edges 表 weight 默认值为 0.5"""
        cursor = storage.conn.execute("PRAGMA table_info(edges)")
        columns = {row[1]: row for row in cursor.fetchall()}
        assert columns["weight"][4] is not None

    def test_sensory_index_table_exists(self, storage):
        """验证 sensory_index 表存在且有正确字段"""
        cursor = storage.conn.execute("PRAGMA table_info(sensory_index)")
        columns = {row[1]: row for row in cursor.fetchall()}
        assert "sense_key" in columns
        assert columns["sense_key"][2] == "TEXT"
        assert columns["sense_key"][3] == "NOT NULL" or columns["sense_key"][3] == 1

        assert "sense_type" in columns
        assert columns["sense_type"][2] == "TEXT"
        assert columns["sense_type"][3] == "NOT NULL" or columns["sense_type"][3] == 1

        assert "node_id" in columns
        assert columns["node_id"][2] == "TEXT"
        assert columns["node_id"][3] == "NOT NULL" or columns["node_id"][3] == 1

        assert "weight" in columns
        assert columns["weight"][2] == "REAL"

        # 验证复合主键：sense_key + node_id
        # PRAGMA table_info 不会直接显示复合主键，验证总字段数
        assert len(columns) == 4

    def test_sensory_index_primary_key(self, storage):
        """验证 sensory_index 的复合主键 (sense_key, node_id)"""
        cursor = storage.conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sensory_index'")
        row = cursor.fetchone()
        assert row is not None
        create_sql = row[0].upper()
        assert "PRIMARY KEY" in create_sql
        assert "SENSE_KEY" in create_sql
        assert "NODE_ID" in create_sql

    def test_seven_indexes_exist(self, storage):
        """验证 7 个索引已创建"""
        cursor = storage.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        expected_indexes = {
            "idx_nodes_type",
            "idx_nodes_content",
            "idx_edges_source",
            "idx_edges_target",
            "idx_edges_rel",
            "idx_sense_key",
            "idx_sense_type",
        }
        # 验证所有期望索引都存在
        assert indexes == expected_indexes, (
            f"期望的索引: {expected_indexes}, 实际索引: {indexes}"
        )
        assert len(indexes) == 7

    def test_insert_and_read_node(self, storage):
        """验证可以插入并查询一条节点记录"""
        storage.conn.execute(
            "INSERT INTO nodes (id, type, content, metadata, edges) "
            "VALUES (?, ?, ?, ?, ?)",
            ("n1", "episodic", "测试记忆", '{"emotion":"happy"}', '[]'),
        )
        storage.conn.commit()

        cursor = storage.conn.execute("SELECT * FROM nodes WHERE id=?", ("n1",))
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "episodic"  # type
        assert row[2] == "测试记忆"  # content

    def test_insert_and_read_edge(self, storage):
        """验证可以插入并查询一条边记录"""
        # 先插入两个节点（外键虽未强制，但逻辑上需要）
        storage.conn.execute(
            "INSERT INTO nodes (id, type, content) VALUES (?, ?, ?)",
            ("n1", "entity", "猫"),
        )
        storage.conn.execute(
            "INSERT INTO nodes (id, type, content) VALUES (?, ?, ?)",
            ("n2", "entity", "鱼"),
        )
        storage.conn.execute(
            "INSERT INTO edges (source_id, target_id, rel, weight) VALUES (?, ?, ?, ?)",
            ("n1", "n2", "likes", 0.9),
        )
        storage.conn.commit()

        cursor = storage.conn.execute(
            "SELECT source_id, target_id, rel, weight FROM edges WHERE source_id=?",
            ("n1",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "n1"
        assert row[1] == "n2"
        assert row[2] == "likes"
        assert row[3] == 0.9

    def test_insert_and_read_sensory_index(self, storage):
        """验证可以插入并查询一条感官索引记录"""
        storage.conn.execute(
            "INSERT INTO nodes (id, type, content) VALUES (?, ?, ?)",
            ("n1", "episodic", "看到红色的花"),
        )
        storage.conn.execute(
            "INSERT INTO sensory_index (sense_key, sense_type, node_id, weight) "
            "VALUES (?, ?, ?, ?)",
            ("红色", "visual", "n1", 0.95),
        )
        storage.conn.commit()

        cursor = storage.conn.execute(
            "SELECT sense_key, sense_type, node_id, weight FROM sensory_index WHERE sense_key=?",
            ("红色",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "红色"
        assert row[1] == "visual"
        assert row[2] == "n1"
        assert row[3] == 0.95

    def test_auto_increment_on_edges(self, storage):
        """验证 edges 表 id 自增"""
        storage.conn.execute(
            "INSERT INTO nodes (id, type, content) VALUES ('n1', 'entity', 'a'), ('n2', 'entity', 'b')"
        )
        storage.conn.execute(
            "INSERT INTO edges (source_id, target_id, rel) VALUES ('n1', 'n2', 'knows')"
        )
        storage.conn.execute(
            "INSERT INTO edges (source_id, target_id, rel) VALUES ('n2', 'n1', 'knows')"
        )
        storage.conn.commit()

        cursor = storage.conn.execute("SELECT id FROM edges ORDER BY id")
        ids = [row[0] for row in cursor.fetchall()]
        assert ids == [1, 2]

    def test_db_path_string(self):
        """验证 db_path 为字符串时创建文件数据库"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            gs = GraphStorage(db_path=db_path)
            assert os.path.exists(db_path)
            gs.close()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_default_db_path_creates_elfie_home(self, monkeypatch, tmp_path):
        elfie_home = tmp_path / "fresh_home"
        monkeypatch.setenv("ELFIE_HOME", str(elfie_home))

        gs = GraphStorage()

        try:
            assert elfie_home.exists()
            assert (elfie_home / "graph_memory.db").exists()
            assert gs.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0] == 0
        finally:
            gs.close()


class TestGraphStorageCRUD:
    """测试 GraphStorage 的 CRUD 操作"""

    @pytest.fixture
    def storage(self):
        """创建内存 SQLite GraphStorage 实例"""
        gs = GraphStorage(db_path=":memory:")
        yield gs

    @pytest.fixture
    def sample_node(self):
        """创建示例节点"""
        return MemoryNode(
            id="test_1",
            type="episodic",
            content="测试记忆内容",
            metadata={"emotion": "happy", "importance": 0.8},
            edges=[Edge(target="entity_1", rel="involves", weight=0.7)],
        )

    def test_add_and_get_node(self, storage, sample_node):
        """添加节点后可按ID获取"""
        node_id = storage.add_node(sample_node)
        assert node_id == "test_1"

        retrieved = storage.get_node("test_1")
        assert retrieved is not None
        assert retrieved.id == "test_1"
        assert retrieved.type == "episodic"
        assert retrieved.content == "测试记忆内容"
        assert retrieved.metadata["emotion"] == "happy"
        assert retrieved.metadata["importance"] == 0.8
        assert len(retrieved.edges) == 1
        assert retrieved.edges[0].target == "entity_1"
        assert retrieved.edges[0].rel == "involves"
        assert retrieved.edges[0].weight == 0.7

    def test_get_node_not_found(self, storage):
        """获取不存在的节点返回None"""
        assert storage.get_node("nonexistent") is None

    def test_add_node_upsert(self, storage):
        """重复添加相同ID节点会更新"""
        node1 = MemoryNode(id="upsert_1", type="episodic", content="原始内容")
        storage.add_node(node1)

        node2 = MemoryNode(
            id="upsert_1", type="episodic", content="更新后的内容",
            metadata={"updated": True},
        )
        storage.add_node(node2)

        retrieved = storage.get_node("upsert_1")
        assert retrieved.content == "更新后的内容"
        assert retrieved.metadata["updated"] is True

    def test_update_node(self, storage, sample_node):
        """更新节点字段"""
        storage.add_node(sample_node)

        result = storage.update_node("test_1", content="更新后的内容")
        assert result is True

        retrieved = storage.get_node("test_1")
        assert retrieved.content == "更新后的内容"
        # 其他字段不变
        assert retrieved.metadata["emotion"] == "happy"

    def test_update_node_not_found(self, storage):
        """更新不存在的节点返回False"""
        result = storage.update_node("nonexistent", content="新内容")
        assert result is False

    def test_update_node_merge_metadata(self, storage, sample_node):
        """metadata合并更新：新字段覆盖旧字段，旧字段保留"""
        storage.add_node(sample_node)

        storage.update_node("test_1", metadata={"importance": 1.0, "new_field": "value"})

        retrieved = storage.get_node("test_1")
        # 旧字段保留
        assert retrieved.metadata["emotion"] == "happy"
        # 新字段覆盖旧值
        assert retrieved.metadata["importance"] == 1.0
        # 新增字段
        assert retrieved.metadata["new_field"] == "value"

    def test_delete_node_soft(self, storage, sample_node):
        """软删除不物理删除，节点仍然存在"""
        storage.add_node(sample_node)

        result = storage.delete_node("test_1")
        assert result is True

        # 软删除后节点仍然可获取
        retrieved = storage.get_node("test_1")
        assert retrieved is not None
        assert retrieved.metadata.get("forgotten") is True

    def test_delete_node_not_found(self, storage):
        """删除不存在的节点返回False"""
        result = storage.delete_node("nonexistent")
        assert result is False

    def test_add_and_get_edges(self, storage):
        """添加边后可查询"""
        storage.add_node(MemoryNode(id="src", type="entity", content="源"))
        storage.add_node(MemoryNode(id="tgt", type="entity", content="目标"))

        edge_id = storage.add_edge("src", "tgt", "likes", 0.9)
        assert edge_id is not None
        assert isinstance(edge_id, int)

        edges = storage.get_edges("src", direction="outgoing")
        assert len(edges) == 1
        assert edges[0].target == "tgt"
        assert edges[0].rel == "likes"
        assert edges[0].weight == 0.9

    def test_get_edges_direction(self, storage):
        """出边/入边/双向"""
        storage.add_node(MemoryNode(id="a", type="entity", content="A"))
        storage.add_node(MemoryNode(id="b", type="entity", content="B"))
        storage.add_node(MemoryNode(id="c", type="entity", content="C"))

        storage.add_edge("a", "b", "knows")
        storage.add_edge("c", "a", "likes")

        outgoing = storage.get_edges("a", direction="outgoing")
        assert len(outgoing) == 1
        assert outgoing[0].target == "b"

        incoming = storage.get_edges("a", direction="incoming")
        assert len(incoming) == 1
        # 入边：c -> a，Edge.target应为c（源节点）
        assert incoming[0].target == "c"
        assert incoming[0].rel == "likes"

        both = storage.get_edges("a", direction="both")
        assert len(both) == 2

    def test_get_edges_no_edges(self, storage):
        """没有边时返回空列表"""
        storage.add_node(MemoryNode(id="isolated", type="entity", content="孤立节点"))
        edges = storage.get_edges("isolated")
        assert edges == []

    def test_get_nodes_by_type(self, storage):
        """按类型查询节点"""
        for i in range(5):
            storage.add_node(MemoryNode(id=f"ep_{i}", type="episodic", content=f"记忆{i}"))
        for i in range(3):
            storage.add_node(MemoryNode(id=f"ent_{i}", type="entity", content=f"实体{i}"))

        episodic_nodes = storage.get_nodes_by_type("episodic")
        assert len(episodic_nodes) == 5

        entity_nodes = storage.get_nodes_by_type("entity")
        assert len(entity_nodes) == 3

    def test_get_nodes_by_type_limit(self, storage):
        """按类型查询带limit"""
        for i in range(10):
            storage.add_node(MemoryNode(id=f"n_{i}", type="episodic", content=f"记忆{i}"))

        nodes = storage.get_nodes_by_type("episodic", limit=3)
        assert len(nodes) == 3

    def test_get_nodes_by_type_empty(self, storage):
        """没有匹配类型时返回空列表"""
        nodes = storage.get_nodes_by_type("nonexistent_type")
        assert nodes == []

    def test_get_unconsolidated_nodes(self, storage):
        """获取未巩固节点"""
        storage.add_node(
            MemoryNode(id="c1", type="episodic", content="已巩固", metadata={"consolidated": True}),
        )
        storage.add_node(MemoryNode(id="u1", type="episodic", content="未巩固1"))
        storage.add_node(
            MemoryNode(id="u2", type="episodic", content="未巩固2", metadata={"consolidated": False}),
        )
        storage.add_node(
            MemoryNode(id="u3", type="episodic", content="未巩固3", metadata={"foo": "bar"}),
        )

        unconsolidated = storage.get_unconsolidated_nodes()
        ids = {n.id for n in unconsolidated}
        assert "c1" not in ids  # 已巩固的排除
        assert "u1" in ids
        assert "u2" in ids
        assert "u3" in ids

    def test_get_unconsolidated_nodes_no_match(self, storage):
        """没有未巩固节点时返回空列表"""
        storage.add_node(
            MemoryNode(id="c1", type="episodic", content="已巩固", metadata={"consolidated": True}),
        )
        unconsolidated = storage.get_unconsolidated_nodes()
        assert len(unconsolidated) == 0

    def test_count_nodes(self, storage):
        """计数节点"""
        assert storage.count_nodes() == 0

        for i in range(5):
            storage.add_node(MemoryNode(id=f"n_{i}", type="episodic", content=f"记忆{i}"))

        assert storage.count_nodes() == 5

    def test_count_nodes_by_type(self, storage):
        """按类型计数节点"""
        for i in range(3):
            storage.add_node(MemoryNode(id=f"ep_{i}", type="episodic", content=f"记忆{i}"))
        for i in range(2):
            storage.add_node(MemoryNode(id=f"ent_{i}", type="entity", content=f"实体{i}"))

        assert storage.count_nodes("episodic") == 3
        assert storage.count_nodes("entity") == 2
        assert storage.count_nodes("knowledge") == 0


class TestGraphStorageTFIDFSearch:
    """测试 GraphStorage 的 TF-IDF 内容搜索"""

    @pytest.fixture
    def storage(self):
        """创建内存 SQLite GraphStorage 实例"""
        gs = GraphStorage(db_path=":memory:")
        # 插入测试数据
        nodes = [
            MemoryNode(id="n1", type="episodic", content="今天天气很好适合出去玩"),
            MemoryNode(id="n2", type="episodic", content="下雨了记得带伞"),
            MemoryNode(id="n3", type="episodic", content="周末去公园散步"),
            MemoryNode(id="n4", type="knowledge", content="Python是一种编程语言"),
            MemoryNode(id="n5", type="knowledge", content="机器学习需要大量数据"),
            MemoryNode(id="n6", type="entity", content="天气"),
        ]
        for node in nodes:
            gs.add_node(node)
        yield gs

    def test_search_by_content_chinese(self, storage):
        """中文关键词查询，返回最相关的节点"""
        results = storage.search_by_content("天气", top_k=3)
        # 按分数降序排列，最相关的应该是包含"天气"的节点
        assert len(results) > 0
        assert results[0][0] in ("n1", "n6")  # 包含"天气"的节点
        # 所有结果的score都应大于0
        for _node_id, score in results:
            assert score > 0.0

    def test_search_by_content_type_filter(self, storage):
        """按类型过滤查询"""
        # 只查询knowledge类型
        results = storage.search_by_content("数据", top_k=5, node_type="knowledge")
        assert len(results) > 0
        # 所有结果都应是knowledge类型
        for node_id, score in results:
            assert node_id in ("n4", "n5")
            assert score > 0.0

        # 查询不存在的类型应返回空
        results = storage.search_by_content("天气", top_k=5, node_type="nonexistent")
        assert results == []

    def test_search_by_content_empty_result(self, storage):
        """空结果查询"""
        # 搜索不相关的内容
        results = storage.search_by_content("xyzxyz", top_k=5)
        assert results == []

    def test_search_by_content_top_k(self, storage):
        """验证top_k参数生效"""
        results = storage.search_by_content("天气", top_k=1)
        assert len(results) == 1

    def test_search_by_content_empty_query(self, storage):
        """空查询返回空列表"""
        assert storage.search_by_content("") == []
        assert storage.search_by_content("   ") == []
