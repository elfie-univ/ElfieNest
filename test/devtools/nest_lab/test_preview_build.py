from pathlib import Path
from types import SimpleNamespace

import pytest

from devtools.nest_lab import preview_build


@pytest.fixture
def build_environment(tmp_path, monkeypatch):
    output = tmp_path / "godot-web"
    output.mkdir()
    for name in ["elfienest.pck", "nest-assets.pck", "nest-assets.json"]:
        (output / name).write_text("old")
    events = []
    state = {"runtime": False, "assets": False, "fail": False}

    def current(folder):
        return (
            state["runtime"]
            if folder == output
            else (folder / "elfienest.pck").read_text() == "new"
        )

    def run(command, **kwargs):
        assert kwargs["cwd"] == preview_build.ROOT
        if command[0] == "bash":
            events.append(command)
            return SimpleNamespace(returncode=0)
        destination = (
            Path(command[command.index("--output") + 1])
            if "--output" in command
            else Path(command[command.index("--web-output") + 1])
        )
        if "--check-nest-assets" in command:
            valid = (
                state["assets"]
                if destination == output
                else (
                    (destination / "nest-assets.pck").is_file()
                    and (destination / "nest-assets.pck").read_text() == "new"
                )
            )
            return SimpleNamespace(returncode=0 if valid else 1)
        events.append(command)
        # Existing previews must remain usable throughout both builds.
        assert (output / "elfienest.pck").read_text() == "old"
        if (output / "nest-assets.pck").exists():
            assert (output / "nest-assets.pck").read_text() == "old"
        if "--web-output" not in command:
            destination.mkdir(exist_ok=True)
            (destination / "elfienest.pck").write_text("new")
        else:
            if state["fail"]:
                raise RuntimeError("asset build failed")
            (destination / "nest-assets.pck").write_text("new")
            (destination / "nest-assets.json").write_text("new")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        preview_build, "current_source_fingerprint", lambda: "unchanged"
    )
    monkeypatch.setattr(preview_build, "runtime_is_current", current)
    monkeypatch.setattr(preview_build.subprocess, "run", run)
    return output, events, state


def test_changed_sources_publish_both_previews_together(build_environment):
    output, events, state = build_environment
    preview_build.ensure_preview_bundle(output)
    assert len(events) == 3
    assert (output / "elfienest.pck").read_text() == "new"
    assert (output / "nest-assets.pck").read_text() == "new"


def test_asset_failure_preserves_both_previous_previews(build_environment):
    output, events, state = build_environment
    state["fail"] = True
    with pytest.raises(RuntimeError, match="asset build failed"):
        preview_build.ensure_preview_bundle(output)
    assert (output / "elfienest.pck").read_text() == "old"
    assert (output / "nest-assets.pck").read_text() == "old"
    assert not list(output.parent.glob(".godot-web.preview-*"))


def test_unchanged_sources_do_not_rebuild(build_environment):
    output, events, state = build_environment
    state.update(runtime=True, assets=True)
    preview_build.ensure_preview_bundle(output)
    assert events == []


def test_missing_asset_pack_is_repaired_even_with_current_runtime(build_environment):
    output, events, state = build_environment
    state["runtime"] = True
    (output / "nest-assets.pck").unlink()
    preview_build.ensure_preview_bundle(output)
    assert (output / "nest-assets.pck").read_text() == "new"


def test_source_changes_during_build_do_not_publish_a_mixed_pair(
    build_environment, monkeypatch
):
    output, events, state = build_environment
    fingerprints = iter(["before", "changed-during-build"])
    monkeypatch.setattr(
        preview_build, "current_source_fingerprint", lambda: next(fingerprints)
    )
    with pytest.raises(RuntimeError, match="sources changed"):
        preview_build.ensure_preview_bundle(output)
    assert (output / "elfienest.pck").read_text() == "old"
    assert (output / "nest-assets.pck").read_text() == "old"
