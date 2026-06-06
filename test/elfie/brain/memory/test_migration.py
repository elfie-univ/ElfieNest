"""数据迁移单元测试

测试 migrate_from_json 函数的功能正确性：
空JSON、完整迁移、幂等性、字段映射、异常处理、文件保护。
"""

import hashlib
import json
import os

import pytest

from elfie.brain.memory.migration import migrate_from_json


class TestMigration:
    """测试 .elfie_memories.json → SQLite 图存储迁移"""

    # ── 辅助方法 ──────────────────────────────────────────────

    def _create_json(self, path: str, data: list):
        """创建临时 JSON 记忆文件"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _read_node_count(self, db_path: str) -> int:
        """读取数据库中的节点总数"""
        from elfie.brain.memory.graph_storage import GraphStorage

        storage = GraphStorage(db_path=db_path)
        count = storage.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        storage.close()
        return count

    def _read_all_nodes(self, db_path: str) -> list:
        """读取数据库中所有节点记录"""
        from elfie.brain.memory.graph_storage import GraphStorage

        storage = GraphStorage(db_path=db_path)
        cursor = storage.conn.execute(
            "SELECT id, type, content, metadata, edges, created_at, updated_at "
            "FROM nodes ORDER BY created_at"
        )
        rows = [dict(row) for row in cursor.fetchall()]
        storage.close()
        return rows

    # ── Fixtures ──────────────────────────────────────────────

    @pytest.fixture
    def sample_data(self):
        """包含各种字段的测试记忆数据"""
        return [
            {
                "content": "主人8点喂了我鱼味食物",
                "metadata": {
                    "emotion": "happy",
                    "intensity": 80.0,
                    "timestamp": "2026-06-03 08:00:00",
                    "level": "episodic",
                    "stimulus": "主人喂食",
                },
            },
            {
                "content": "今天下午在公园追蝴蝶",
                "metadata": {
                    "emotion": "excited",
                    "intensity": 65.0,
                    "timestamp": "2026-06-03 15:30:00",
                    "level": "episodic",
                    "location": "公园",
                    "tags": {"weather": "sunny", "mood": "playful"},
                },
            },
            {
                "content": "晚上被窗外的雷声吓到",
                "metadata": {
                    "emotion": "fear",
                    "intensity": 90.0,
                    "timestamp": "2026-06-03 22:00:00",
                    "level": "consolidated",
                    "stimulus": "雷声",
                },
            },
        ]

    # ── 测试用例 ──────────────────────────────────────────────

    def test_migrate_empty_json(self, tmp_path):
        """空JSON迁移应返回0"""
        json_path = str(tmp_path / "empty.json")
        db_path = str(tmp_path / "empty.db")
        self._create_json(json_path, [])

        count = migrate_from_json(json_path, db_path)
        assert count == 0
        assert self._read_node_count(db_path) == 0

    def test_migrate_full_data(self, tmp_path, sample_data):
        """迁移实际数据，节点数与源数据一致"""
        json_path = str(tmp_path / "full.json")
        db_path = str(tmp_path / "full.db")
        self._create_json(json_path, sample_data)

        count = migrate_from_json(json_path, db_path)
        assert count == len(sample_data)
        assert self._read_node_count(db_path) == len(sample_data)

    def test_idempotent(self, tmp_path, sample_data):
        """运行两次迁移结果一致"""
        json_path = str(tmp_path / "idempotent.json")
        db_path = str(tmp_path / "idempotent.db")
        self._create_json(json_path, sample_data)

        # 第一次迁移
        count1 = migrate_from_json(json_path, db_path)
        assert count1 == len(sample_data)
        assert self._read_node_count(db_path) == len(sample_data)

        # 第二次迁移（幂等：相同 content+timestamp 应跳过）
        count2 = migrate_from_json(json_path, db_path)
        assert count2 == 0  # 全部已存在，无新增
        assert self._read_node_count(db_path) == len(sample_data)  # 总量不变

    def test_field_mapping(self, tmp_path):
        """验证字段映射正确性：emotion、intensity、timestamp、level等"""
        json_path = str(tmp_path / "mapping.json")
        db_path = str(tmp_path / "mapping.db")

        data = [
            {
                "content": "测试记忆一条",
                "metadata": {
                    "emotion": "happy",
                    "intensity": 80.0,
                    "timestamp": "2026-06-03 08:00:00",
                    "level": "episodic",
                    "stimulus": "测试刺激",
                },
            }
        ]
        self._create_json(json_path, data)

        migrate_from_json(json_path, db_path)
        nodes = self._read_all_nodes(db_path)
        assert len(nodes) == 1

        node = nodes[0]
        meta = json.loads(node["metadata"])

        # type 固定为 episodic
        assert node["type"] == "episodic"

        # content 原样保留
        assert node["content"] == "测试记忆一条"

        # emotion 保留在 metadata 中
        assert meta["emotion"] == "happy"

        # timestamp → created_at
        assert node["created_at"] == "2026-06-03 08:00:00"

        # intensity → emotion_intensity（80/100 = 0.8）
        assert meta["emotion_intensity"] == 0.8

        # level 被丢弃，metadata 中没有 level 字段
        assert "level" not in meta

        # 其他字段保留
        assert meta["stimulus"] == "测试刺激"

        # edges 为空数组
        assert node["edges"] == "[]"

    def test_field_mapping_zero_intensity(self, tmp_path):
        """intensity为0时，emotion_intensity应为0.0"""
        json_path = str(tmp_path / "zero_intensity.json")
        db_path = str(tmp_path / "zero_intensity.db")

        data = [
            {
                "content": "零强度记忆",
                "metadata": {
                    "emotion": "neutral",
                    "intensity": 0.0,
                    "timestamp": "2026-06-03 12:00:00",
                    "level": "episodic",
                },
            }
        ]
        self._create_json(json_path, data)

        migrate_from_json(json_path, db_path)
        nodes = self._read_all_nodes(db_path)
        meta = json.loads(nodes[0]["metadata"])
        assert meta["emotion_intensity"] == 0.0

    def test_field_mapping_tags_merged(self, tmp_path):
        """metadata.tags 应合并到 metadata"""
        json_path = str(tmp_path / "tags.json")
        db_path = str(tmp_path / "tags.db")

        data = [
            {
                "content": "带标签的记忆",
                "metadata": {
                    "emotion": "sad",
                    "intensity": 30.0,
                    "timestamp": "2026-06-04 10:00:00",
                    "level": "episodic",
                    "tags": {"weather": "rainy", "mood": "melancholy"},
                },
            }
        ]
        self._create_json(json_path, data)

        migrate_from_json(json_path, db_path)
        nodes = self._read_all_nodes(db_path)
        meta = json.loads(nodes[0]["metadata"])

        # tags 中的字段已合并到 metadata
        assert meta["weather"] == "rainy"
        assert meta["mood"] == "melancholy"
        # tags 本身不应保留在 metadata 中
        assert "tags" not in meta

    def test_invalid_json_file_not_exists(self, tmp_path):
        """JSON文件不存在时应返回0"""
        db_path = str(tmp_path / "nofile.db")
        count = migrate_from_json("/tmp/nonexistent_memories.json", db_path)
        assert count == 0

    def test_invalid_json_malformed(self, tmp_path):
        """格式错误的JSON应返回0"""
        json_path = str(tmp_path / "malformed.json")
        db_path = str(tmp_path / "malformed.db")

        with open(json_path, "w", encoding="utf-8") as f:
            f.write("这不是 JSON 格式的内容 {{{")

        count = migrate_from_json(json_path, db_path)
        assert count == 0
        assert self._read_node_count(db_path) == 0

    def test_preserve_original(self, tmp_path, sample_data):
        """原JSON文件在迁移后不应被修改"""
        json_path = str(tmp_path / "preserve.json")
        db_path = str(tmp_path / "preserve.db")
        self._create_json(json_path, sample_data)

        # 迁移前计算文件哈希
        with open(json_path, "rb") as f:
            before = hashlib.md5(f.read()).hexdigest()

        migrate_from_json(json_path, db_path)

        # 迁移后计算文件哈希
        with open(json_path, "rb") as f:
            after = hashlib.md5(f.read()).hexdigest()

        assert before == after, "原JSON文件在迁移后被修改"

    def test_migrate_large_dataset(self, tmp_path):
        """迁移100条记忆数据集"""
        json_path = str(tmp_path / "large.json")
        db_path = str(tmp_path / "large.db")

        # 生成100条模拟记忆
        large_data = []
        for i in range(100):
            large_data.append(
                {
                    "content": f"模拟记忆第{i+1}条内容描述",
                    "metadata": {
                        "emotion": "happy" if i % 2 == 0 else "sad",
                        "intensity": float(i),
                        "timestamp": f"2026-06-{(i // 10) + 1:02d} {(i % 24):02d}:{(i * 3) % 60:02d}:00",
                        "level": "episodic",
                    },
                }
            )
        self._create_json(json_path, large_data)

        count = migrate_from_json(json_path, db_path)
        assert count == 100
        assert self._read_node_count(db_path) == 100
