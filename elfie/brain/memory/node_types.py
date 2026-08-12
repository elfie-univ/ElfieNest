"""图记忆系统的数据模型定义。

包含 MemoryNode（记忆节点）、Edge（边）、RetrievalQuery（检索查询）等核心数据结构。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union, cast

JsonValue = Union[
    None,
    bool,
    int,
    float,
    str,
    List["JsonValue"],
    Dict[str, "JsonValue"],
]


class MemoryMetadata(dict[str, JsonValue]):
    """Named JSON metadata container shared by Brain and its storage Port.

    The container preserves the historical mapping ergonomics used by memory
    algorithms while validating that values are serializable domain data. It
    deliberately excludes arbitrary Python objects and SDK/SQL records.
    """

    def __init__(self, values: Optional[Mapping[str, object]] = None) -> None:
        super().__init__()
        if values is not None:
            self.update(values)

    def __setitem__(self, key: str, value: JsonValue) -> None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("memory metadata keys must be non-blank strings")
        super().__setitem__(key, self._normalize(value))

    def update(self, *args: Any, **kwargs: Any) -> None:
        """Validate every mutation instead of bypassing ``__setitem__``."""
        if len(args) > 1:
            raise TypeError(f"update expected at most 1 argument, got {len(args)}")
        if args:
            values = args[0]
            if hasattr(values, "items"):
                items = values.items()
            else:
                items = values
            for key, value in items:
                self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def copy(self) -> MemoryMetadata:
        return MemoryMetadata(self)

    def to_dict(self) -> Dict[str, JsonValue]:
        return dict(self)

    @classmethod
    def _normalize(cls, value: object) -> JsonValue:
        if value is None or isinstance(value, (bool, int, float, str)):
            return cast(JsonValue, value)
        if isinstance(value, Mapping):
            return {str(key): cls._normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._normalize(item) for item in value]
        raise TypeError(
            f"memory metadata only accepts JSON values, got {type(value).__name__}"
        )


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

    target: str  # 目标节点ID
    rel: str  # 边类型（EdgeTypes值）
    weight: float = 0.5  # 边权重（0~1）


@dataclass
class MemoryNode:
    """记忆节点：图中的顶点，代表一条记忆"""

    id: str
    type: str  # NodeTypes值
    content: str
    metadata: Dict[str, Any] = field(default_factory=MemoryMetadata)
    edges: List[Edge] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, MemoryMetadata):
            self.metadata = MemoryMetadata(self.metadata)


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
