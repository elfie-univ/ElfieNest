"""Fresh checkouts must test asset contents, never Git LFS pointer bytes."""

import subprocess
from types import SimpleNamespace

import pytest

from scripts.quality.validation import test_bundles

POINTER = (
    b"version https://git-lfs.github.com/spec/v1\noid sha256:placeholder\nsize 20\n"
)


def test_lfs_inputs_are_downloaded_before_the_test_entry_proceeds(
    tmp_path, monkeypatch
):
    asset = tmp_path / "model.glb"
    asset.write_bytes(POINTER)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["cwd"] == tmp_path and kwargs["check"]
        if "pull" in command:
            asset.write_bytes(b"glTF-real-model")
        return SimpleNamespace(stdout="model.glb\n")

    monkeypatch.setattr(test_bundles.subprocess, "run", run)
    test_bundles.prepare_lfs_test_inputs(tmp_path)
    assert len(calls) == 2
    assert calls[1] == ["git", "lfs", "pull", "--include=model.glb", "--exclude="]
    assert asset.read_bytes() == b"glTF-real-model"
    calls.clear()
    test_bundles.prepare_lfs_test_inputs(tmp_path)
    assert len(calls) == 1


def test_lfs_download_failure_is_not_treated_as_valid_asset_data(tmp_path, monkeypatch):
    (tmp_path / "model.glb").write_bytes(POINTER)

    def run(command, **kwargs):
        if "pull" in command:
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(stdout="model.glb\n")

    monkeypatch.setattr(test_bundles.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        test_bundles.prepare_lfs_test_inputs(tmp_path)
