from elfie.profile import (
    ELFARIA_CANON,
    ElfieOrigin,
    create_visual_profile,
    get_species_canon,
    get_species_canon_for_technical_id,
)


def test_formal_species_names_are_distinct_from_earth_shape_labels() -> None:
    saevi = get_species_canon("saevi")
    tovren = get_species_canon("tovren")
    myelle = get_species_canon("myelle")

    assert (saevi.display_name, saevi.earth_shape_label) == ("Saevi", "fox-like")
    assert (tovren.display_name, tovren.earth_shape_label) == ("Tovren", "dog-like")
    assert (myelle.display_name, myelle.earth_shape_label) == ("Myelle", "cat-like")
    assert saevi.visual_runtime_supported is True
    assert tovren.visual_runtime_supported is True
    assert myelle.visual_runtime_supported is False
    assert get_species_canon_for_technical_id("fox").canon_id == "saevi"
    assert get_species_canon_for_technical_id("dog").canon_id == "tovren"
    assert get_species_canon_for_technical_id("cat").canon_id == "myelle"


def test_profile_round_trip_preserves_world_origin_and_arrival_facts() -> None:
    profile = create_visual_profile(
        elfie_id="origin-check",
        display_name="Lumi",
        species_id="fox",
        seed=17,
        origin=ElfieOrigin(
            home_region_id=ELFARIA_CANON.known_region_id,
            birth_at="Elfaria-local:late-autumn",
        ),
    )

    restored = type(profile).from_dict(profile.to_dict())

    assert restored.identity.origin.home_world_id == "elfaria"
    assert restored.identity.origin.home_region_id == "mistyville"
    assert restored.identity.origin.birth_at == "Elfaria-local:late-autumn"
    assert restored.identity.origin.arrival_base_id == "elfie_nest"
