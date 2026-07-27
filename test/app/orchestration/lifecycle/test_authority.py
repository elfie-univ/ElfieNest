from __future__ import annotations

from pathlib import Path

import pytest

from app.orchestration.lifecycle import authority as authority_module
from app.orchestration.lifecycle.authority import AuthorityLifecycleConfig
from godot_runtime.host_contract import RuntimeHostKind
from godot_runtime.launcher import AuthorityLaunchPlan, AuthorityLaunchRequest


def test_recorded_authority_pid_uses_the_verified_stop_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a later Supervisor invocation has only the private receipt PID.
    stopped: list[tuple[int, AuthorityLaunchRequest]] = []
    config = AuthorityLifecycleConfig(tmp_path, 18180, 18181, "new-stop-nonce")
    request = AuthorityLaunchRequest(tmp_path, 18180, 18181, "new-stop-nonce")
    recorded = type("RecordedAuthority", (), {"pid": 18182})()
    monkeypatch.setattr(
        authority_module,
        "_stop_recorded_authority",
        lambda pid, launch_request: stopped.append((pid, launch_request)),
        raising=False,
    )
    _, stop = authority_module.authority_lifecycle(config)

    # When: lifecycle stops the persisted authority identity.
    stop(recorded)

    # Then: it delegates to the exact-PID identity-verifying stop path.
    assert stopped == [(18182, request)]


def test_recorded_linux_dedicated_authority_matches_its_exported_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = tmp_path / "build/components/godot-linux-dedicated/ElfieNestRuntime"
    binary.parent.mkdir(parents=True)
    binary.touch()
    request = AuthorityLaunchRequest(tmp_path, 18180, 18181, "dedicated-nonce")
    plan = AuthorityLaunchPlan(
        RuntimeHostKind.LINUX_DEDICATED,
        (str(binary.resolve()),),
        tmp_path.resolve(),
        (),
    )

    class Inspector:
        def cwd(self, _pid: int) -> Path:
            return tmp_path

        def command(self, _pid: int) -> tuple[str, ...]:
            return (str(binary.resolve()),)

    monkeypatch.setattr(authority_module, "DefaultProcessInspector", Inspector)
    monkeypatch.setattr(
        authority_module,
        "plan_godot_runtime_launch",
        lambda _request: plan,
    )

    assert authority_module._recorded_authority_matches(18182, request) is True
