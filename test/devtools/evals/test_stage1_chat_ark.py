import json
from pathlib import Path

from devtools.evals.stage1_chat_ark import _build_bundle

ROOT = Path(__file__).resolve().parents[3]


def test_frozen_e1_fixture_compiles_through_typed_world_canon() -> None:
    spec = json.loads(
        (ROOT / "devtools/evals/stage1_e1_scenarios.json").read_text(encoding="utf-8")
    )
    bundle = _build_bundle(spec, "e1-typed-fixture", "Lumi")

    assert spec["schema_version"] == "stage1-e1.v2"
    assert bundle.manifest.canon_version == "elfaria-world.v0.1"
    assert len(bundle.knowledge_seeds) >= 30
    assert [episode.seed_id for episode in bundle.episode_seeds] == [
        "early-home",
        "learning-path",
        "shared-space-choice",
        "departure-decision",
        "arrival-nest",
    ]
    assert len(bundle.relationship_seeds) == 13
    assert bundle.memory_seeds == ()
    assert all(seed.source == "canon" for seed in bundle.knowledge_seeds)
    assert all(seed.source_ref.startswith("canon:") for seed in bundle.knowledge_seeds)
