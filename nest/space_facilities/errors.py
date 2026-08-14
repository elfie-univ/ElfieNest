"""Errors owned by the semantic space and facilities owner."""

from __future__ import annotations


class UnknownAnchorError(RuntimeError):
    def __init__(self, anchor_id: str) -> None:
        super().__init__(anchor_id)
        self.anchor_id = anchor_id

    def __str__(self) -> str:
        return f"未知或不可用 anchor: {self.anchor_id}"


__all__ = ("UnknownAnchorError",)
