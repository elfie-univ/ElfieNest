from __future__ import annotations

import stat
from pathlib import Path

import pytest

from ai_runtime.storage.data_layout import (
    InvalidAvatarExtensionError,
    InvalidFinalElfieIdError,
    InvalidFinalUserIdError,
    UnsafeDataLayoutPathError,
    ensure_final_elfie_layout,
    ensure_final_root_layout,
    ensure_final_user_layout,
    final_root_layout,
)


def _relative_directories(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_dir() and not path.is_symlink()
    }


def test_final_root_layout_exposes_only_final_paths(tmp_path: Path) -> None:
    # Given: an explicit, empty data root.
    root = tmp_path / "data"

    # When: the final root paths are resolved without ensuring the layout.
    layout = final_root_layout(root)

    # Then: paths follow the final contract and no filesystem entry is created.
    assert layout.nest_database == root / "nest.db"
    assert layout.providers_config == root / "configs" / "providers.yaml"
    assert layout.auth_env == root / "configs" / "auth.env"
    assert layout.runtime_config == root / "configs" / "runtime.yaml"
    assert layout.food_packages == root / "configs" / "food-packages.yaml"
    assert layout.model_validations == root / "reports" / "model-validations"
    assert layout.runtime_state == root / "runtime" / "runtime.json"
    assert layout.token_usage_log == root / "logs" / "token_usage.jsonl"
    assert not root.exists()


def test_ensure_final_root_layout_creates_exact_secure_directories(
    tmp_path: Path,
) -> None:
    # Given: an explicit, empty data root.
    root = tmp_path / "data"

    # When: the final root layout is ensured twice.
    ensure_final_root_layout(root)
    ensure_final_root_layout(root)

    # Then: only final directories exist and every one is owner-only.
    expected = {
        Path("assets"),
        Path("assets/users"),
        Path("configs"),
        Path("configs/credentials"),
        Path("configs/food-packages-history"),
        Path("elfies"),
        Path("logs"),
        Path("reports"),
        Path("reports/model-validations"),
        Path("reports/runtime-validations"),
        Path("runtime"),
        Path("runtime/locks"),
    }
    assert _relative_directories(root) == expected
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert all(stat.S_IMODE((root / path).stat().st_mode) == 0o700 for path in expected)
    assert not any(path.is_file() for path in root.rglob("*"))


def test_ensure_final_user_layout_uses_numeric_id_and_secure_files_dir(
    tmp_path: Path,
) -> None:
    # Given: an explicit, empty data root.
    root = tmp_path / "data"

    # When: a final user layout is ensured.
    layout = ensure_final_user_layout(root, "42")

    # Then: the final asset paths exist without creating an avatar file.
    assert layout.assets == root / "assets" / "users" / "42"
    assert layout.files == layout.assets / "files"
    assert layout.avatar("JPEG") == layout.assets / "avatar.jpeg"
    assert stat.S_IMODE(layout.assets.stat().st_mode) == 0o700
    assert stat.S_IMODE(layout.files.stat().st_mode) == 0o700
    assert not layout.avatar("png").exists()


@pytest.mark.parametrize("user_id", ["", "-1", "user-1", "1/2", "１"])
def test_ensure_final_user_layout_rejects_invalid_id_before_writes(
    tmp_path: Path,
    user_id: str,
) -> None:
    # Given: an explicit, empty data root and an invalid user ID.
    root = tmp_path / "data"

    # When / Then: parsing fails before any directory is written.
    with pytest.raises(InvalidFinalUserIdError):
        ensure_final_user_layout(root, user_id)
    assert not root.exists()


@pytest.mark.parametrize("extension", ["", "gif", ".png", "png/other", "svg"])
def test_final_user_avatar_rejects_unsupported_extension(
    tmp_path: Path,
    extension: str,
) -> None:
    # Given: a parsed final user layout.
    layout = final_root_layout(tmp_path / "data").user("42")

    # When / Then: an unsupported avatar extension is rejected.
    with pytest.raises(InvalidAvatarExtensionError):
        layout.avatar(extension)


def test_ensure_final_elfie_layout_creates_complete_secure_workspace(
    tmp_path: Path,
) -> None:
    # Given: an explicit, empty data root.
    root = tmp_path / "data"

    # When: a final Elfie layout is ensured.
    layout = ensure_final_elfie_layout(root, "00000042")

    # Then: all final workspace directories and database paths are present.
    expected = {
        layout.workspace,
        layout.assets,
        layout.godot,
        layout.profile.parent,
        layout.skills,
        layout.history_database.parent,
        layout.attachments,
        layout.knowledge_database.parent,
        layout.daily_memory,
        layout.people_memory,
        layout.concepts_memory,
    }
    assert layout.profile == layout.workspace / "profile" / "profile.yaml"
    assert (
        layout.history_database == layout.workspace / "conversations" / "history.sqlite"
    )
    assert layout.knowledge_database == layout.workspace / "memory" / "knowledge.sqlite"
    assert all(path.is_dir() for path in expected)
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 for path in expected)
    assert not layout.profile.exists()
    assert not layout.history_database.exists()
    assert not layout.knowledge_database.exists()


@pytest.mark.parametrize("elfie_id", ["", "42", "000000042", "elfie_42", "0000/042"])
def test_ensure_final_elfie_layout_rejects_non_eight_digit_id_before_writes(
    tmp_path: Path,
    elfie_id: str,
) -> None:
    # Given: an explicit, empty data root and an invalid Elfie ID.
    root = tmp_path / "data"

    # When / Then: parsing fails before any directory is written.
    with pytest.raises(InvalidFinalElfieIdError):
        ensure_final_elfie_layout(root, elfie_id)
    assert not root.exists()


def test_ensure_final_root_layout_rejects_root_symlink(tmp_path: Path) -> None:
    # Given: a data-root path that is itself a symlink.
    target = tmp_path / "target"
    target.mkdir()
    root = tmp_path / "data"
    root.symlink_to(target, target_is_directory=True)

    # When / Then: layout creation refuses to follow it.
    with pytest.raises(UnsafeDataLayoutPathError):
        ensure_final_root_layout(root)
    assert list(target.iterdir()) == []


def test_ensure_final_root_layout_rejects_symlink_in_existing_ancestor(
    tmp_path: Path,
) -> None:
    # Given: a missing data root below an existing symlinked ancestor.
    outside = tmp_path / "outside"
    outside.mkdir()
    redirected_parent = tmp_path / "redirected"
    redirected_parent.symlink_to(outside, target_is_directory=True)
    root = redirected_parent / "nested" / "data"

    # When / Then: preflight rejects the ancestor before writing outside the path.
    with pytest.raises(UnsafeDataLayoutPathError):
        ensure_final_root_layout(root)
    assert list(outside.iterdir()) == []


def test_ensure_final_root_layout_rejects_nested_symlink_without_partial_writes(
    tmp_path: Path,
) -> None:
    # Given: an existing root with a final directory redirected by symlink.
    root = tmp_path / "data"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "configs").symlink_to(outside, target_is_directory=True)

    # When / Then: the preflight rejects it without writing through the link.
    with pytest.raises(UnsafeDataLayoutPathError):
        ensure_final_root_layout(root)
    assert list(outside.iterdir()) == []
    assert set(root.iterdir()) == {root / "configs"}
