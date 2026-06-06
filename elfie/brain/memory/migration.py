"""记忆数据迁移工具：将 .elfie_memories.json 旧格式迁移到 SQLite 图存储。

迁移映射规则：
- 每条旧记忆 → 一个 episodic 节点
- content → content
- metadata.emotion → metadata.emotion
- metadata.timestamp → created_at
- metadata.intensity → metadata.emotion_intensity（除以100转为0-1范围）
- metadata.level → 丢弃（全部设为type='episodic'）
- metadata.tags → 合并到metadata
- 旧记忆edges设为空数组
- metadata中其他字段保留到metadata
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List

from elfie.brain.memory.graph_storage import GraphStorage

logger = logging.getLogger("elfie.brain.memory.migration")


def migrate_from_json(json_path: str, db_path: str) -> int:
    """将 .elfie_memories.json 迁移到 SQLite 图存储

    Args:
        json_path: .elfie_memories.json 文件路径
        db_path: SQLite 数据库文件路径

    Returns:
        迁移的节点数量（跳过已存在的重复记录）
    """
    json_file = Path(json_path)
    if not json_file.exists():
        logger.warning(f"记忆文件不存在: {json_path}，跳过迁移")
        return 0

    with open(json_file, encoding="utf-8") as f:
        try:
            old_memories: List[Dict[str, Any]] = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"记忆文件格式错误: {e}")
            return 0

    if not old_memories:
        logger.info("记忆文件为空，无需迁移")
        return 0

    storage = GraphStorage(db_path=db_path)
    migrated_count = 0

    try:
        for entry in old_memories:
            content = entry.get("content", "")
            meta = entry.get("metadata", {})

            # 提取时间戳作为 created_at
            timestamp = meta.get("timestamp", "")

            # 幂等性检查：通过 content + created_at 去重
            existing = storage.conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE content = ? AND created_at = ?",
                (content, timestamp),
            ).fetchone()[0]
            if existing > 0:
                continue

            # 构建新 metadata：排除 timestamp、level，转换 intensity
            new_meta: Dict[str, Any] = {}
            for key, value in meta.items():
                if key in ("timestamp", "level"):
                    # timestamp → created_at（已放入节点字段）
                    # level → 丢弃（统一使用 type='episodic'）
                    continue
                if key == "intensity":
                    # intensity 0-100 转为 emotion_intensity 0.0-1.0
                    try:
                        intensity_val = float(value)
                    except (ValueError, TypeError):
                        intensity_val = 0.0
                    new_meta["emotion_intensity"] = round(intensity_val / 100.0, 4)
                elif key == "tags" and isinstance(value, dict):
                    # tags 合并到 metadata
                    new_meta.update(value)
                else:
                    new_meta[key] = value

            # 生成唯一节点 ID
            node_id = uuid.uuid4().hex

            # 插入数据库
            storage.conn.execute(
                "INSERT INTO nodes (id, type, content, metadata, edges, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    node_id,
                    "episodic",
                    content,
                    json.dumps(new_meta, ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),  # 旧记忆edges设为空数组
                    timestamp,
                    None,
                ),
            )
            migrated_count += 1

        storage.conn.commit()
        logger.info(f"✅ [迁移完成] 成功迁移 {migrated_count} 条记忆到 {db_path}")
    except Exception:
        storage.conn.rollback()
        raise
    finally:
        storage.close()

    return migrated_count
