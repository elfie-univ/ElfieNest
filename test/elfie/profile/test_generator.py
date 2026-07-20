from elfie.profile import (
    AppearanceGenerator,
    create_visual_profile,
    get_species_profile,
)


def test_same_seed_and_choices_generate_same_appearance() -> None:
    first = AppearanceGenerator(7357).generate(
        species_id="fox", height_direction="tall", build_direction="plump"
    )
    second = AppearanceGenerator(7357).generate(
        species_id="fox", height_direction="tall", build_direction="plump"
    )
    assert first == second


def test_display_name_does_not_change_appearance() -> None:
    first = create_visual_profile(
        elfie_id="same-id",
        display_name="甲",
        species_id="dog",
        seed=91,
    )
    second = create_visual_profile(
        elfie_id="same-id",
        display_name="乙",
        species_id="dog",
        seed=91,
    )
    assert first.appearance == second.appearance


def test_species_colors_are_selected_from_profile() -> None:
    for species_id in ("dog", "fox"):
        profile = get_species_profile(species_id)
        for seed in range(20):
            genome = AppearanceGenerator(seed).generate(species_id=species_id)
            assert genome.coat.palette_id in profile.palettes
            assert genome.coat.pattern_id in profile.patterns
            assert genome.coat.eye_color_id in profile.eye_colors
            assert genome.coat.nose_color_id in profile.nose_colors


def test_generated_profile_validates_for_many_seeds() -> None:
    for seed in range(100):
        profile = create_visual_profile(
            elfie_id=f"e-{seed}",
            display_name="测试精灵",
            species_id="fox" if seed % 2 else "dog",
            seed=seed,
            height_direction=("short", "standard", "tall")[seed % 3],
            build_direction=("slim", "standard", "plump")[seed % 3],
        )
        profile.validate()


def test_species_private_traits_do_not_pollute_other_species() -> None:
    dog = AppearanceGenerator(12).generate(species_id="dog")
    fox = AppearanceGenerator(12).generate(species_id="fox")
    assert set(dog.species_traits) == {
        "jowl_fullness_bias",
        "ear_fold_bias",
        "tail_curl_bias",
    }
    assert set(fox.species_traits) == {
        "black_leg_coverage",
        "tail_tip_coverage",
        "cheek_ruff_bias",
    }
