import math
import sqlite3
from typing import List, Optional, Tuple

from .tokenizer import tokenize


class GraphContentSearchMixin:
    conn: sqlite3.Connection

    def search_by_content(
        self, query: str, top_k: int = 5, node_type: Optional[str] = None
    ) -> List[Tuple[str, float]]:
        if not query:
            return []

        query_words = tokenize(query)
        if not query_words:
            return []

        if node_type:
            cursor = self.conn.execute(
                "SELECT id, content FROM nodes WHERE type=?", (node_type,)
            )
        else:
            cursor = self.conn.execute("SELECT id, content FROM nodes")

        scored: List[Tuple[str, float]] = []
        for row in cursor.fetchall():
            content_words = tokenize(row["content"])
            intersection = set(query_words) & set(content_words)
            if not intersection:
                score = 0.0
            else:
                score = len(intersection) / (
                    math.sqrt(len(query_words)) * math.sqrt(len(content_words))
                )

            if score > 0.0:
                scored.append((row["id"], score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
