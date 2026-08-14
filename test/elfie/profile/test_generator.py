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
    for species_id in ("dog", "fox", "cat"):
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
    cat = AppearanceGenerator(12).generate(species_id="cat")
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
    assert set(cat.species_traits) == {
        "whisker_sensitivity_bias",
        "ear_focus_bias",
        "tail_balance_bias",
    }


def test_explicit_overrides_control_generated_appearance() -> None:
    profile = create_visual_profile(
        elfie_id="configured-fox",
        display_name="栗子",
        species_id="fox",
        seed=42,
        appearance_overrides={
            "macro": {
                "stature_z": 1.75,
                "frame_size_z": -0.4,
                "body_fat_z": 1.2,
                "muscularity_z": 0.3,
            },
            "face": {"skull_width_bias": -0.65, "eye_size_bias": 0.4},
            "coat": {"palette_id": "silver", "eye_color_id": "green"},
            "species_traits": {"tail_tip_coverage": 0.8},
        },
    )

    assert profile.appearance.macro.stature_z == 1.75
    assert profile.appearance.macro.body_fat_z == 1.2
    assert profile.appearance.face.skull_width_bias == -0.65
    assert profile.appearance.face.eye_size_bias == 0.4
    assert profile.appearance.coat.palette_id == "silver"
    assert profile.appearance.coat.eye_color_id == "green"
    assert profile.appearance.species_traits["tail_tip_coverage"] == 0.8


def test_overrides_reject_unknown_and_out_of_range_parameters() -> None:
    for overrides in (
        {"face": {"unknown_face_control": 0.2}},
        {"macro": {"stature_z": 2.1}},
        {"species_traits": {"dog_only_trait": 0.1}},
    ):
        try:
            create_visual_profile(
                elfie_id="invalid-fox",
                display_name="越界",
                species_id="fox",
                seed=42,
                appearance_overrides=overrides,
            )
        except ValueError:
            continue
        raise AssertionError(f"外貌覆盖应被拒绝: {overrides}")
