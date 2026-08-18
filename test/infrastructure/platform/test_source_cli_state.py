import json
import os
import stat
from pathlib import Path

import pytest

from infrastructure.platform.source_cli_state import (
    SourceCliState,
    SourceCliStateError,
)


def test_source_state_is_outside_product_root_and_is_lazy(tmp_path: Path) -> None:
    source = tmp_path / "checkout"
    source.mkdir()
    product = source / ".elfienest.local"
    state = SourceCliState(source)

    assert not state.control_dir.exists()
    state.record_candidate(product, detail="default")

    assert state.control_dir.parent == source
    assert state.control_dir != product
    assert not product.exists()
    assert state.load_candidates()[0].home == product.resolve()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission contract")
def test_source_state_uses_owner_only_permissions(tmp_path: Path) -> None:
    (tmp_path / "checkout").mkdir()
    state = SourceCliState(tmp_path / "checkout")
    state.record_history("status")
    state.record_candidate(tmp_path / "task")

    assert stat.S_IMODE(state.control_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(state.history_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(state.candidate_path.stat().st_mode) == 0o600


def test_sensitive_history_is_not_persisted(tmp_path: Path) -> None:
    (tmp_path / "checkout").mkdir()
    state = SourceCliState(tmp_path / "checkout")

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

    assert SourceCliState(source).load_candidates() == ()


def test_symlinked_control_state_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "checkout"
    target = tmp_path / "elsewhere"
    target.mkdir()
    source.mkdir()
    (source / ".elfienest-cli.local").symlink_to(target, target_is_directory=True)

    with pytest.raises(SourceCliStateError):
        SourceCliState(source).record_candidate(tmp_path / "task")


def test_candidate_catalog_has_no_runtime_authority_fields(tmp_path: Path) -> None:
    (tmp_path / "checkout").mkdir()
    state = SourceCliState(tmp_path / "checkout")
    state.record_candidate(tmp_path / "task", detail="observed")

    payload = json.loads(state.candidate_path.read_text(encoding="utf-8"))
    assert set(payload) == {"version", "homes"}
    assert set(payload["homes"][0]) == {"home", "detail"}
