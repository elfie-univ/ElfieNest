from __future__ import annotations

import json
from pathlib import Path

import pytest

from devtools.brain_eval.artifacts import BrainEvalArtifactStore


def test_artifacts_are_confined_to_root_build_directory(tmp_path: Path) -> None:
    store = BrainEvalArtifactStore(tmp_path, "run-001")

    path = store.write_json("decision.json", {"status": "observe"})

    assert path == tmp_path / "build" / "brain-eval" / "run-001" / "decision.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "observe"}

    with pytest.raises(ValueError, match="build/brain-eval"):
        BrainEvalArtifactStore(
            tmp_path,
            "run-002",
            output_root=tmp_path / "outside",
        )


def test_run_artifacts_are_append_only_and_cannot_be_reopened(tmp_path: Path) -> None:
    store = BrainEvalArtifactStore(tmp_path, "run-immutable")
    store.write_json("decision.json", {"status": "observe"})

    with pytest.raises(ValueError, match="already exists"):
        BrainEvalArtifactStore(tmp_path, "run-immutable")
    with pytest.raises(ValueError, match="already exists"):
        store.write_json("decision.json", {"status": "promote"})
