import json
import os
import stat
from pathlib import Path

import pytest

from app.orchestration.lifecycle.ports import LifecycleLocalPaths
from infrastructure.platform.source_cli_state import (
    SourceCliState,
    SourceCliStateError,
)


def _source_state(source_root: Path) -> SourceCliState:
    home = (source_root / ".elfienest.local").resolve(strict=False)
    return SourceCliState(
        LifecycleLocalPaths(
            home=home,
            logs=home / "logs",
            model_validations=home / "reports" / "model-validations",
            runtime_validations=home / "reports" / "runtime-validations",
            runtime_state=home / "runtime" / "runtime.json",
            runtime_locks=home / "runtime" / "locks",
            source_cli_state=home / "runtime" / "cli",
        )
    )


def test_source_state_is_optional_under_default_product_runtime_and_lazy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "checkout"
    source.mkdir()
    product = source / ".elfienest.local"
    state = _source_state(source)

    assert not state.control_dir.exists()
    assert state.load_history() == ()
    assert state.load_candidates() == ()
    assert not product.exists()

    state.record_candidate(product, detail="default")

    assert state.control_dir == product / "runtime" / "cli"
    assert state.load_candidates()[0].home == product.resolve()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission contract")
def test_source_state_uses_owner_only_permissions(tmp_path: Path) -> None:
    (tmp_path / "checkout").mkdir()
    state = _source_state(tmp_path / "checkout")
    state.record_history("status")
    state.record_candidate(tmp_path / "task")

    assert stat.S_IMODE(state.control_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(state.history_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(state.candidate_path.stat().st_mode) == 0o600


def test_sensitive_history_is_not_persisted(tmp_path: Path) -> None:
    (tmp_path / "checkout").mkdir()
    state = _source_state(tmp_path / "checkout")

    assert state.record_history("owner --password super-secret") is False
    assert state.record_history("start --token super-secret") is False
    assert not state.control_dir.exists()

    assert state.record_history("start --data-home 'data A'") is True
    assert state.load_history() == ("start --data-home 'data A'",)


def test_old_selected_home_receipt_is_never_read(tmp_path: Path) -> None:
    source = tmp_path / "checkout"
    legacy = source / ".elfienest.local" / "runtime"
    legacy.mkdir(parents=True)
    (legacy / "selected-data-home").write_text(
        str(tmp_path / "legacy-task"), encoding="utf-8"
    )

    assert _source_state(source).load_candidates() == ()


def test_symlinked_control_state_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "checkout"
    target = tmp_path / "elsewhere"
    target.mkdir()
    source.mkdir()
    runtime = source / ".elfienest.local" / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "cli").symlink_to(target, target_is_directory=True)

    with pytest.raises(SourceCliStateError):
        _source_state(source).load_candidates()
    with pytest.raises(SourceCliStateError):
        _source_state(source).record_candidate(tmp_path / "task")


def test_non_directory_control_state_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "checkout"
    control_path = source / ".elfienest.local" / "runtime" / "cli"
    control_path.parent.mkdir(parents=True)
    control_path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(SourceCliStateError):
        _source_state(source).load_candidates()
    with pytest.raises(SourceCliStateError):
        _source_state(source).record_candidate(tmp_path / "task")


def test_legacy_top_level_control_state_is_not_read_or_migrated(
    tmp_path: Path,
) -> None:
    source = tmp_path / "checkout"
    legacy = source / ".elfienest-cli.local"
    legacy.mkdir(parents=True)
    (legacy / "history").write_text("status\n", encoding="utf-8")
    (legacy / "data-homes.json").write_text(
        '{"version": 1, "homes": [{"home": "/legacy", "detail": "old"}]}\n',
        encoding="utf-8",
    )
    state = _source_state(source)

    assert state.load_history() == ()
    assert state.load_candidates() == ()
    assert not state.control_dir.exists()
    assert (legacy / "history").read_text(encoding="utf-8") == "status\n"


def test_candidate_catalog_has_no_runtime_authority_fields(tmp_path: Path) -> None:
    (tmp_path / "checkout").mkdir()
    state = _source_state(tmp_path / "checkout")
    state.record_candidate(tmp_path / "task", detail="observed")

    payload = json.loads(state.candidate_path.read_text(encoding="utf-8"))
    assert set(payload) == {"version", "homes"}
    assert set(payload["homes"][0]) == {"home", "detail"}
