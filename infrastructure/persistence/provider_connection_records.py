"""Persistence-only decoding for the Provider connection document."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

from infrastructure.models.provider_records import (
    CONNECTION_DOCUMENT_VERSION,
    ProviderConnection,
)

_CATALOG_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class InvalidProviderConnectionDocument(ValueError):
    """The v2 Provider connection document is malformed."""


@dataclass(frozen=True)
class ProviderConnectionDocument:
    """Decoded durable Provider document owned by Persistence."""

    version: int = CONNECTION_DOCUMENT_VERSION
    counters: Dict[str, int] = field(default_factory=dict)
    connections: Dict[str, ProviderConnection] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": CONNECTION_DOCUMENT_VERSION,
            "connection_counters": dict(sorted(self.counters.items())),
            "connections": {
                key: value.to_dict() for key, value in self.connections.items()
            },
        }


def parse_provider_document(raw: Mapping[str, Any]) -> ProviderConnectionDocument:
    """Decode one YAML mapping without exposing YAML details to Model callers."""
    version = raw.get("version")
    if version != CONNECTION_DOCUMENT_VERSION:
        raise InvalidProviderConnectionDocument(
            f"只支持 Provider 连接配置 v2，收到版本: {version!r}"
        )
    raw_counters = raw.get("connection_counters", {})
    raw_connections = raw.get("connections", {})
    if not isinstance(raw_counters, Mapping) or not isinstance(
        raw_connections, Mapping
    ):
        raise InvalidProviderConnectionDocument(
            "connection_counters 和 connections 必须是对象"
        )
    counters: Dict[str, int] = {}
    for catalog_id, value in raw_counters.items():
        if (
            not isinstance(catalog_id, str)
            or _CATALOG_ID_PATTERN.fullmatch(catalog_id) is None
        ):
            raise InvalidProviderConnectionDocument(f"无效 catalog_id: {catalog_id!r}")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InvalidProviderConnectionDocument(f"无效连接序号: {catalog_id}")
        counters[catalog_id] = value
    connections: Dict[str, ProviderConnection] = {}
    try:
        for connection_id, value in raw_connections.items():
            if not isinstance(connection_id, str) or not isinstance(value, Mapping):
                raise ValueError("连接配置必须是对象")
            connections[connection_id] = ProviderConnection.from_dict(
                connection_id, value
            )
    except ValueError as exc:
        raise InvalidProviderConnectionDocument(str(exc)) from exc
    return ProviderConnectionDocument(counters=counters, connections=connections)


__all__ = (
    "InvalidProviderConnectionDocument",
    "ProviderConnectionDocument",
    "parse_provider_document",
)
