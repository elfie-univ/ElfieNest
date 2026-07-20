from devtools.elfie_lab.schemas import ElfieSpec, calculate_state_diff


def test_calculate_state_diff_only_keeps_changed_fields():
    before = {"energy": 100.0, "emotions": {"happiness": 50.0, "fear": 10.0}}
    after = {"energy": 99.5, "emotions": {"happiness": 55.0, "fear": 10.0}}

    assert calculate_state_diff(before, after) == {
        "energy": {"before": 100.0, "after": 99.5},
        "emotions": {"happiness": {"before": 50.0, "after": 55.0}},
    }


def test_legacy_lab_spec_migrates_anatomy_to_default_species():
    spec = ElfieSpec.from_dict(
        {"elfie_id": "elfie_legacy", "name": "旧精灵", "anatomy_type": "quadruped"}
    )

    assert spec.species_id == "fox"
    assert "anatomy_type" not in spec.to_dict()
