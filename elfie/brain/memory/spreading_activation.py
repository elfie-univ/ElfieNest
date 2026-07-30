"""扩散激活：从种子节点出发，沿边传播激活值"""

from typing import Dict, List, Tuple

from .memory_store import MemoryStore


class SpreadingActivation:
    """扩散激活：从种子节点出发，沿边扩散激活值"""

    def __init__(self, storage: MemoryStore):
        self.storage = storage

    def spread(
        self,
        seed_node_ids: List[str],
        max_hops: int = 2,
        decay: float = 0.5,
        threshold: float = 0.1,
    ) -> Dict[str, float]:
        """扩散激活算法

        参数：
        - seed_node_ids: 种子节点ID列表（初始激活值1.0）
        - max_hops: 最大跳数（默认2）
        - decay: 衰减系数（默认0.5，每跳激活值×decay）
        - threshold: 激活阈值（默认0.1，低于此值的节点不纳入结果）

        返回：{node_id: activation_score} 字典

        算法：
        1. 初始化：种子节点激活值=1.0
        2. 每跳：从当前激活节点出发，沿边扩散
        3. 新激活值 = 源激活值 × decay × edge_weight
        4. 必须有visited-set防止循环（同一节点只激活一次）
        5. 低于threshold的节点不纳入结果
        6. 返回所有激活值≥threshold的节点
        """
        activation: Dict[str, float] = {}
        visited: set = set(seed_node_ids)

        # 初始化：种子节点激活值=1.0
        for nid in seed_node_ids:
            activation[nid] = 1.0

        current_frontier: Dict[str, float] = dict.fromkeys(seed_node_ids, 1.0)

        for _ in range(max_hops):
            next_frontier: Dict[str, float] = {}

            for node_id, source_activation in current_frontier.items():
                neighbors = self._get_neighbors(node_id)
                for neighbor_id, edge_weight in neighbors:
                    if neighbor_id in visited:
                        continue

                    # 新激活值 = 源激活值 × decay × edge_weight
                    new_activation = source_activation * decay * edge_weight

                    if new_activation < threshold:
                        continue

                    visited.add(neighbor_id)
                    next_frontier[neighbor_id] = new_activation
                    activation[neighbor_id] = new_activation

            current_frontier = next_frontier
            if not current_frontier:
                break

        return activation

    def _get_neighbors(self, node_id: str) -> List[Tuple[str, float]]:
        """获取节点的邻居（通过出边和入边）

        返回 [(neighbor_id, edge_weight), ...]
        """
        edges = self.storage.get_edges(node_id, direction="both")
        return [(edge.target, edge.weight) for edge in edges]
