"""图记忆系统的数据模型定义。

包含 MemoryNode（记忆节点）、Edge（边）、RetrievalQuery（检索查询）等核心数据结构。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeTypes(str, Enum):
    """节点类型枚举"""
    EPISODIC = "episodic"
    ENTITY = "entity"
    KNOWLEDGE = "knowledge"
    PATTERN = "pattern"


class EdgeTypes(str, Enum):
    """边类型枚举"""
    INVOLVES = "involves"
    TEMPORAL = "temporal"
    EMOTIONAL = "emotional"
    CAUSAL = "causal"
    SUPPORTS = "supports"
    ABOUT = "about"
    IMPLIES = "implies"


@dataclass
class Edge:
    """边：连接两个记忆节点的有向关系"""
    target: str          # 目标节点ID
    rel: str             # 边类型（EdgeTypes值）
    weight: float = 0.5  # 边权重（0~1）


@dataclass
class MemoryNode:
    """记忆节点：图中的顶点，代表一条记忆"""
    id: str
    type: str            # NodeTypes值
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class RetrievalQuery:
    """检索查询：描述当前上下文，用于检索相关记忆"""
    text_query: str = ""
    current_emotion: str = ""
    current_intensity: float = 0.0
    current_entities: List[str] = field(default_factory=list)
    current_time: str = ""
    current_sensory: Dict[str, str] = field(default_factory=dict)
    recent_events: List[str] = field(default_factory=list)
