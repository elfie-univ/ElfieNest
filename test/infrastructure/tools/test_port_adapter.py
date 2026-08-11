from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from elfie.brain.tool_port import ToolRequest
from infrastructure.tools.observation import (
    PermissionDecisionObservation,
    ToolCallObservation,
)
from infrastructure.tools.port_adapter import DisabledToolPort, ToolPortAdapter


@dataclass
class RecordingObservationPort:
    tool_calls: list[ToolCallObservation] = field(default_factory=list)
    permissions: list[PermissionDecisionObservation] = field(default_factory=list)

    def record_tool_observation(self, observation: ToolCallObservation) -> None:
        self.tool_calls.append(observation)

    def record_permission_observation(
        self, observation: PermissionDecisionObservation
    ) -> None:
        self.permissions.append(observation)


@dataclass
class FakeSearchPlugin:
    queries: list[str] = field(default_factory=list)

    def search(self, query: str) -> str:
        self.queries.append(query)
        return "bounded facts"


@dataclass
class FakePermissionManager:
    actions: list[str] = field(default_factory=list)

    def verify_action(
        self, action: str, file_path: str | None = None, token: str | None = None
    ) -> bool:
        del file_path, token
        self.actions.append(action)
        return True


def _config(*, web_search: bool = True, local_file: bool = False):
    return SimpleNamespace(
        runtime_policy={
            "tools": {
                "web_search": {"enabled": web_search},
                "local_file": {"enabled": local_file},
            }
        }
    )


def _adapter(
    config: object,
    observer: RecordingObservationPort,
    search: FakeSearchPlugin,
    permissions: FakePermissionManager,
    *,
    resolver=None,
    allowed: tuple[str, ...] = ("web_search", "local_file"),
) -> ToolPortAdapter:
    return ToolPortAdapter(
        config=config,
        search_plugin=search,
        permission_manager=permissions,
        observation_port=observer,
        workspace_resolver=resolver,
        allowed_tool_keys=allowed,
    )


def test_adapter_intersects_brain_scope_and_live_runtime_availability() -> None:
    config = _config()
    observer = RecordingObservationPort()
    search = FakeSearchPlugin()
    permissions = FakePermissionManager()
    adapter = _adapter(config, observer, search, permissions, allowed=("web_search",))

    assert adapter.available_tool_keys() == ("web_search",)
    result = adapter.execute(
        ToolRequest(tool_key="web_search", operation="search", query="ElfieNest")
    )

    assert result.ok is True
    assert search.queries == ["ElfieNest"]
    assert permissions.actions == ["WEB_SEARCH"]
    assert len(observer.tool_calls) == 1

    config.runtime_policy["tools"]["web_search"]["enabled"] = False
    assert adapter.available_tool_keys() == ()


def test_adapter_resolves_local_file_root_from_scope_id(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("private facts", encoding="utf-8")
    observer = RecordingObservationPort()
    permissions = FakePermissionManager()
    adapter = _adapter(
        _config(web_search=False, local_file=True),
        observer,
        FakeSearchPlugin(),
        permissions,
        resolver=lambda scope_id: tmp_path if scope_id == "elfie-1" else None,
        allowed=("local_file",),
    )

    result = adapter.execute(
        ToolRequest(
            scope_id="elfie-1",
            tool_key="local_file",
            operation="read",
            resource_id="notes.txt",
        )
    )

    assert result.ok is True
    assert "private facts" in result.content
    assert permissions.actions == ["READ"]
    assert result.retained_bytes > 0


def test_disabled_port_returns_a_typed_denial() -> None:
    result = DisabledToolPort().execute(
        ToolRequest(tool_key="web_search", operation="search", query="facts")
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "tool_unavailable"
