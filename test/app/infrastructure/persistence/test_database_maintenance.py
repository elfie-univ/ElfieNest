from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure.persistence.database_maintenance import (
    UnsafeDatabaseResetError,
    validate_destructive_reset_target,
)


def test_destructive_reset_requires_one_explicit_safe_root(tmp_path: Path) -> None:
    selected_root = (tmp_path / "selected-root").resolve()
    database = selected_root / "nest.db"

    assert (
        validate_destructive_reset_target(
            database,
            expected_data_home=selected_root,
        )
        == selected_root
    )

    with pytest.raises(UnsafeDatabaseResetError):
        validate_destructive_reset_target(
            Path("/nest.db"),
            expected_data_home=selected_root,
        )
    with pytest.raises(UnsafeDatabaseResetError):
        validate_destructive_reset_target(
            Path.home() / ".elfienest" / "nest.db",
            expected_data_home=selected_root,
        )
    with pytest.raises(UnsafeDatabaseResetError):
        validate_destructive_reset_target(
            selected_root / "nest.db",
            expected_data_home=tmp_path / "another-root",
        )
