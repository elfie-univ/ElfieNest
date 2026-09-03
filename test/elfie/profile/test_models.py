import pytest

from elfie.profile import create_visual_profile


def test_profile_dict_round_trip() -> None:
    profile = create_visual_profile(
        elfie_id="elfie-roundtrip",
        display_name="团子",
        species_id="dog",
        seed=1234,
        height_direction="short",
        build_direction="plump",
    )
    assert profile.identity.species_id == "dog"
    assert profile.appearance.genome_version == 2
    assert profile.appearance.species_profile_version > 0
    assert type(profile).from_dict(profile.to_dict()) == profile


def test_unknown_species_is_rejected() -> None:
    with pytest.raises(ValueError, match="species_id"):
        create_visual_profile(
            elfie_id="elfie-invalid",
            display_name="未知",
            species_id="dragon",
            seed=1,
        )
