"""CLI target context and source-candidate revalidation.

The resolver itself is pure.  This module gathers read-only observations from
the lifecycle facade and keeps the interactive session target in memory only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple

from app.orchestration.lifecycle import (
    DataHomeState,
    EntrypointMode,
    LifecycleFacade,
    ResolvedTaskTarget,
    RuntimeComponent,
    RuntimePhase,
    TargetCandidate,
    TargetNotFound,
    TargetResolutionRequest,
    TargetSelectionRequired,
    command_target_policy,
    resolve_installed_data_home,
    resolve_source_default,
    resolve_target,
)


@dataclass
class CliSession:
    """In-memory source-shell context; it is intentionally not persisted."""

    data_home: Optional[Path] = None
    display_data_home: Optional[str] = None


@dataclass(frozen=True)
class _ObservedTarget:
    home: Path
    recognized: bool
    running: bool
    usable: bool
    recoverable: bool
    detail: str


def resolve_cli_target(
    lifecycle: LifecycleFacade,
    *,
    command: str,
    mode: EntrypointMode,
    source_root: Path,
    invoking_cwd: Path,
    explicit_home: Optional[str] = None,
    session: Optional[CliSession] = None,
    installed_environment: Optional[dict[str, str]] = None,
    candidate_selection: Optional[Path] = None,
    prompt: Optional[Callable[[Tuple[TargetCandidate, ...]], Path]] = None,
) -> ResolvedTaskTarget:
    """Resolve one command target and optionally ask for a TTY candidate."""

    if mode is EntrypointMode.INSTALLED:
        target = resolve_target(
            TargetResolutionRequest(
                mode=mode,
                command=command,
                policy=command_target_policy(command),
                source_root=source_root,
                invoking_cwd=invoking_cwd,
                explicit_home=explicit_home,
                default_home=resolve_installed_data_home(
                    installed_environment or {}, user_home=Path.home()
                ),
            )
        )
        if session is not None:
            session.data_home = target.home
            session.display_data_home = target.display_home
        return target

    policy = command_target_policy(command)
    default_home = resolve_source_default(source_root)
    verify_running = policy.default_policy.value == "running"
    default_observation = _observe(
        lifecycle,
        default_home,
        source_root,
        verify_running=verify_running,
    )
    default_eligible = _eligible(default_observation, policy.default_policy.value)

    try:
        state_factory = getattr(lifecycle, "source_cli_state", None)
        source_state = state_factory(source_root) if callable(state_factory) else None
    except (OSError, RuntimeError, ValueError):
        source_state = None
    candidates = tuple(
        candidate
        for candidate in _candidate_targets(
            lifecycle,
            source_root,
            source_state,
            policy.default_policy.value,
        )
        if candidate.home != default_home
    )
    if (
        command in {"stop", "restart"}
        and candidates
        and not default_observation.recognized
    ):
        default_eligible = False
    session_eligible = True
    if session is not None and session.data_home is not None:
        session_observation = _observe(
            lifecycle,
            session.data_home,
            source_root,
            verify_running=policy.default_policy.value == "running",
        )
        session_eligible = _eligible(
            session_observation,
            policy.default_policy.value,
        )
    request = TargetResolutionRequest(
        mode=mode,
        command=command,
        policy=policy,
        source_root=source_root,
        invoking_cwd=invoking_cwd,
        explicit_home=explicit_home,
        session_home=session.data_home if session is not None else None,
        session_display_home=(
            session.display_data_home if session is not None else None
        ),
        session_eligible=session_eligible,
        default_home=default_home,
        default_eligible=default_eligible,
        candidates=candidates,
        selected_candidate=candidate_selection,
    )
    try:
        target = resolve_target(request)
    except TargetSelectionRequired as error:
        if prompt is None:
            raise
        selected = prompt(error.candidates)
        target = resolve_target(
            TargetResolutionRequest(
                **{
                    **request.__dict__,
                    "selected_candidate": selected,
                }
            )
        )

    try:
        inspection = lifecycle.inspect_data_home(
            str(target.home),
            project_root=source_root,
            runtime_mode="development",
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise TargetNotFound(command, str(error)) from error
    if inspection.state is DataHomeState.PERMISSION:
        raise TargetNotFound(command, inspection.detail)

    if session is not None:
        session.data_home = target.home
        session.display_data_home = target.display_home
    _record_candidate_safely(source_state, target.home, target.provenance.value)
    return target


def source_root_for_cli() -> Path:
    """Derive the checkout from this module, never caller mode variables."""

    return Path(__file__).resolve().parents[3]


def _candidate_targets(
    lifecycle: LifecycleFacade,
    source_root: Path,
    state,
    policy_name: str,
) -> Tuple[TargetCandidate, ...]:
    if state is None:
        return ()
    try:
        catalog = state.load_candidates()
    except (OSError, RuntimeError, ValueError):
        return ()
    result = []
    for candidate in catalog:
        observed = _observe(
            lifecycle,
            candidate.home,
            source_root,
            verify_running=policy_name == "running",
        )
        if _eligible(observed, policy_name):
            result.append(TargetCandidate(candidate.home, observed.detail))
    return tuple(result)


def _observe(
    lifecycle: LifecycleFacade,
    home: Path,
    project_root: Path,
    *,
    verify_running: bool = False,
) -> _ObservedTarget:
    canonical = home.resolve(strict=False)
    try:
        inspection = lifecycle.inspect_data_home(
            str(canonical),
            project_root=project_root,
            runtime_mode="development",
        )
    except (OSError, RuntimeError, ValueError) as error:
        return _ObservedTarget(canonical, False, False, False, False, str(error))

    try:
        snapshot = lifecycle.runtime_snapshot(canonical)
    except (OSError, RuntimeError, ValueError) as error:
        return _ObservedTarget(canonical, False, False, False, False, str(error))
    recognized = (
        snapshot.instance_id != "uninitialized"
        and snapshot.phase is not RuntimePhase.RECOVERY_REQUIRED
    )
    running = recognized and snapshot.phase not in {
        RuntimePhase.OFFLINE,
        RuntimePhase.FAILED,
    }
    verified_pid = None
    if running and verify_running:
        verifier = getattr(lifecycle, "existing_service_command", None)
        if not callable(verifier):
            running = False
        else:
            try:
                verified = verifier(canonical, project_root)
            except (OSError, RuntimeError, ValueError):
                verified = None
            if verified is None:
                running = False
            else:
                verified_pid = verified[0]
    usable = inspection.state.value in {"fresh", "partial", "ready"}
    detail = inspection.detail
    if running and verify_running:
        detail = _runtime_candidate_detail(snapshot, verified_pid)
    return _ObservedTarget(
        canonical,
        recognized,
        running,
        usable,
        inspection.recoverable,
        detail,
    )


def _runtime_candidate_detail(snapshot, verified_pid: Optional[int]) -> str:
    """Format the revalidated Runtime facts shown in a task selector."""
    core_pid = verified_pid or snapshot.component(RuntimeComponent.CORE).pid
    gateway_pid = snapshot.component(RuntimeComponent.GATEWAY).pid
    godot_pid = snapshot.component(RuntimeComponent.GODOT_AUTHORITY).pid
    endpoints = {endpoint.name: endpoint.port for endpoint in snapshot.endpoints}
    return (
        f"运行中 · {snapshot.phase.value.upper()} · generation={snapshot.generation}"
        f" · PID core={core_pid or '-'} · gateway={gateway_pid or '-'}"
        f" · godot={godot_pid or '-'}"
        f" · HTTP={endpoints.get('http', '-')} · WS={endpoints.get('godot_ws', '-')}"
    )


def _eligible(observed: _ObservedTarget, policy_name: str) -> bool:
    if policy_name == "always":
        return True
    if policy_name == "recognized":
        return observed.recognized
    if policy_name == "running":
        return observed.running
    if policy_name == "usable":
        return observed.usable or observed.recognized
    if policy_name == "recoverable":
        return observed.usable or observed.recognized or observed.recoverable
    return False


def _record_candidate_safely(state, home: Path, detail: str) -> None:
    if state is None:
        return
    try:
        state.record_candidate(home, detail=detail)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"⚠️ 源码 CLI 候选目录不可写，已继续执行: {error}")


def prompt_for_candidate(candidates: Iterable[TargetCandidate]) -> Path:
    """Prompt once and return a path; validation happens again in the resolver."""

    choices = tuple(candidates)
    print("请选择要操作的数据任务:")
    for index, candidate in enumerate(choices, start=1):
        detail = f" ({candidate.detail})" if candidate.detail else ""
        print(f"  {index}. {_display_candidate_home(candidate.home)}{detail}")
    answer = input("请输入序号: ").strip()
    try:
        index = int(answer) - 1
        return choices[index].home
    except (ValueError, IndexError) as error:
        raise TargetNotFound("selection", "无效的数据任务序号") from error


def _display_candidate_home(home: Path) -> str:
    """Keep selector paths compact without changing the canonical target."""
    canonical = home.expanduser().resolve(strict=False)
    for base, prefix in (
        (Path.cwd().resolve(), ""),
        (Path.home().resolve(), "~/"),
    ):
        try:
            relative = canonical.relative_to(base)
        except ValueError:
            continue
        value = str(relative)
        return f"{prefix}{value}" if value != "." else (prefix or ".")
    return str(canonical)


__all__ = (
    "CliSession",
    "prompt_for_candidate",
    "resolve_cli_target",
    "source_root_for_cli",
)
