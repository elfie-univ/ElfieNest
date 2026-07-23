import json
from pathlib import Path

import pytest

from devtools.elfie_lab.recycle_store import InvalidRecycleIdError, RecycleStore


def _write_source(root: Path, category: str, elfie_id: str, name: str) -> Path:
    path = root / category / elfie_id
    path.mkdir(parents=True)
    (path / name).write_text(category, encoding="utf-8")
    return path


def test_recycle_moves_all_data_into_manifested_bundle(tmp_path):
    # Given
    elfie_id = "elfie_recycle"
    for category in ("elfies", "sessions", "media"):
        _write_source(tmp_path, category, elfie_id, f"{category}.txt")

    # When
    result = RecycleStore(tmp_path).recycle(elfie_id)

    # Then
    assert result.moved_sources == (
        f"elfies/{elfie_id}",
        f"sessions/{elfie_id}",
        f"media/{elfie_id}",
    )
    manifest = json.loads((result.bundle_dir / "manifest.json").read_text())
    assert manifest["deleted_elfie_id"] == elfie_id
    assert manifest["moved_sources"] == list(result.moved_sources)
    for category in ("elfies", "sessions", "media"):
        assert not (tmp_path / category / elfie_id).exists()
        assert (result.bundle_dir / category / elfie_id / f"{category}.txt").is_file()


def test_recycle_rolls_back_every_completed_move_when_later_move_fails(tmp_path):
    # Given
    elfie_id = "elfie_rollback"
    elfie_source = _write_source(tmp_path, "elfies", elfie_id, "profile.json")
    session_source = _write_source(tmp_path, "sessions", elfie_id, "turn.json")
    move_count = 0

    def fail_second_move(source: Path, destination: Path) -> None:
        nonlocal move_count
        move_count += 1
        if move_count == 2:
            raise OSError("injected session move failure")
        source.rename(destination)

    # When
    with pytest.raises(OSError, match="injected session move failure"):
        RecycleStore(tmp_path, move_path=fail_second_move).recycle(elfie_id)

    # Then
    assert (elfie_source / "profile.json").is_file()
    assert (session_source / "turn.json").is_file()
    assert not list((tmp_path / "trash").glob("*"))


@pytest.mark.parametrize("elfie_id", ["../outside", "elfie/child", "", "elfie.$"])
def test_recycle_rejects_unsafe_id_without_touching_data(tmp_path, elfie_id):
    # Given
    outside = tmp_path / "outside"
    outside.mkdir()

    # When
    with pytest.raises(InvalidRecycleIdError):
        RecycleStore(tmp_path).recycle(elfie_id)

    # Then
    assert outside.is_dir()
    assert not (tmp_path / "trash").exists()
