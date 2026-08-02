import sqlite3
from typing import List

from .node_types import Edge


class GraphEdgeStoreMixin:
    conn: sqlite3.Connection

    def add_edge(
        self, source_id: str, target_id: str, rel: str, weight: float = 0.5
    ) -> int:
        cursor = self.conn.execute(
            "INSERT INTO edges (source_id, target_id, rel, weight) VALUES (?, ?, ?, ?)",
            (source_id, target_id, rel, weight),
        )
        self.conn.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("edge insert did not return a row id")
        return cursor.lastrowid

    def get_edges(self, node_id: str, direction: str = "outgoing") -> List[Edge]:
        if direction == "outgoing":
            cursor = self.conn.execute(
                "SELECT target_id, rel, weight FROM edges WHERE source_id=?", (node_id,)
            )
            rows = cursor.fetchall()
            return [
                Edge(target=r["target_id"], rel=r["rel"], weight=r["weight"])
                for r in rows
            ]
        if direction == "incoming":
            cursor = self.conn.execute(
                "SELECT source_id, rel, weight FROM edges WHERE target_id=?", (node_id,)
            )
            rows = cursor.fetchall()
            return [
                Edge(target=r["source_id"], rel=r["rel"], weight=r["weight"])
                for r in rows
            ]

        cursor = self.conn.execute(
            "SELECT source_id, target_id, rel, weight FROM edges WHERE source_id=? OR target_id=?",
            (node_id, node_id),
        )
        rows = cursor.fetchall()
        edges = []
        for r in rows:
            if r["source_id"] == node_id:
                edges.append(
                    Edge(target=r["target_id"], rel=r["rel"], weight=r["weight"])
                )
            else:
                edges.append(
                    Edge(target=r["source_id"], rel=r["rel"], weight=r["weight"])
                )
        return edges
