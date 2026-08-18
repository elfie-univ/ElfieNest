from pathlib import Path

import pytest

from app.orchestration.lifecycle.target_resolution import (
    EntrypointMode,
    ExplicitTargetNotSupported,
    InvalidCandidateSelection,
    TargetCandidate,
    TargetNotFound,
    TargetProvenance,
    TargetResolutionRequest,
    TargetSelectionRequired,
    command_target_policy,
    resolve_installed_data_home,
    resolve_source_default,
    resolve_target,
)


def _request(tmp_path: Path, **changes) -> TargetResolutionRequest:
    values = {
        "mode": EntrypointMode.SOURCE,
        "command": "status",
        "policy": command_target_policy("status"),
        "source_root": tmp_path / "source",
        "invoking_cwd": tmp_path / "caller",
    }
    values.update(changes)
    return TargetResolutionRequest(**values)


def test_installed_root_is_exactly_env_or_default_and_ignores_cwd() -> None:
    user_home = Path("/Users/tester").resolve()

    assert resolve_installed_data_home(
        {"ELFIE_HOME": "relative-prod"}, user_home=user_home
    ) == (user_home / "relative-prod").resolve()
    assert resolve_installed_data_home({}, user_home=user_home) == (
        user_home / ".elfienest"
    ).resolve()
    assert resolve_installed_data_home(
        {"ELFIE_HOME": ""}, user_home=user_home
    ) == (user_home / ".elfienest").resolve()


def test_source_default_never_reads_caller_elfie_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "unrelated-installed-root"))

    assert resolve_source_default(tmp_path / "checkout") == (
        tmp_path / "checkout" / ".elfienest.local"
    ).resolve()


def test_explicit_source_target_wins_and_is_relative_to_invoking_cwd(
    tmp_path: Path,
) -> None:
    target = resolve_target(
        _request(
            tmp_path,
            command="restart",
            policy=command_target_policy("restart"),
            invoking_cwd=tmp_path / "caller",
            explicit_home="data A",
        )
    )

    assert target.home == (tmp_path / "caller" / "data A").resolve()
    assert target.provenance is TargetProvenance.EXPLICIT


def test_session_target_is_authoritative_even_when_default_is_idle(
    tmp_path: Path,
) -> None:
    session = tmp_path / "task-A"
    target = resolve_target(
        _request(
            tmp_path,
            command="stop",
            policy=command_target_policy("stop"),
            session_home=session,
            default_home=tmp_path / ".elfienest.local",
            default_eligible=False,
            candidates=(TargetCandidate(tmp_path / "task-B"),),
        )
    )

    assert target.home == session.resolve()
    assert target.provenance is TargetProvenance.SESSION


def test_idle_default_does_not_suppress_running_candidate_selection(
    tmp_path: Path,
) -> None:
    candidates = (TargetCandidate(tmp_path / "task-A"), TargetCandidate(tmp_path / "task-B"))

    with pytest.raises(TargetSelectionRequired) as error:
        resolve_target(
            _request(
                tmp_path,
                command="stop",
                policy=command_target_policy("stop"),
                default_home=tmp_path / ".elfienest.local",
                default_eligible=False,
                candidates=candidates,
            )
        )

    assert tuple(item.home for item in error.value.candidates) == tuple(
        item.home.resolve() for item in candidates
    )


def test_candidate_selection_is_revalidated_and_deduplicated(tmp_path: Path) -> None:
    task = tmp_path / "task-A"
    target = resolve_target(
        _request(
            tmp_path,
            command="status",
            candidates=(
                TargetCandidate(task),
                TargetCandidate(task / ".." / task.name),
            ),
            selected_candidate=task,
        )
    )

    assert target.home == task.resolve()
    assert target.provenance is TargetProvenance.CANDIDATE

    with pytest.raises(InvalidCandidateSelection):
        resolve_target(
            _request(
                tmp_path,
                command="status",
                candidates=(TargetCandidate(task),),
                selected_candidate=tmp_path / "other",
            )
        )


def test_explicit_home_is_rejected_for_non_lifecycle_source_commands(
    tmp_path: Path,
) -> None:
    with pytest.raises(ExplicitTargetNotSupported):
        resolve_target(
            _request(
                tmp_path,
                command="web",
                policy=command_target_policy("web"),
                explicit_home=str(tmp_path / "task"),
            )
        )


def test_no_target_is_typed_when_no_default_or_candidate_exists(tmp_path: Path) -> None:
    with pytest.raises(TargetNotFound):
        resolve_target(_request(tmp_path))
