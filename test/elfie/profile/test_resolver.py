from dataclasses import replace

from elfie.profile import AppearanceResolver, create_visual_profile


def _profile():
    return create_visual_profile(
        elfie_id="elfie-resolve",
        display_name="豆包",
        species_id="dog",
        seed=99,
    )


def test_signed_value_activates_only_one_shape_key_direction() -> None:
    profile = _profile()
    face = replace(profile.appearance.face, skull_width_bias=-0.7)
    profile = replace(profile, appearance=replace(profile.appearance, face=face))

    shapes = AppearanceResolver().resolve(profile).blend_shapes
    assert shapes["Face_SkullWidth_Pos"] == 0.0
    assert shapes["Face_SkullWidth_Neg"] == 0.7


def test_high_body_fat_makes_main_soft_tissue_regions_fuller() -> None:
    profile = _profile()
    neutral_bias = replace(
        profile.appearance.body_bias,
        belly_depth_bias=0.0,
        arm_thickness_bias=0.0,
        leg_thickness_bias=0.0,
        neck_thickness_bias=0.0,
    )
    neutral_face = replace(profile.appearance.face, cheek_fullness_bias=0.0)
    macro = replace(
        profile.appearance.macro,
        body_fat_z=1.8,
        frame_size_z=0.0,
        muscularity_z=0.0,
    )
    profile = replace(
        profile,
        appearance=replace(
            profile.appearance,
            macro=macro,
            body_bias=neutral_bias,
            face=neutral_face,
        ),
    )

    shapes = AppearanceResolver().resolve(profile).blend_shapes
    for name in (
        "Body_BellyDepth_Pos",
        "Body_ArmThickness_Pos",
        "Body_LegThickness_Pos",
        "Body_NeckThickness_Pos",
        "Face_CheekFullness_Pos",
    ):
        assert shapes[name] > 0.0


def test_payload_contains_explicit_species_and_all_parameter_groups() -> None:
    payload = AppearanceResolver().resolve(_profile()).to_payload()
    assert payload["species_id"] == "dog"
    assert payload["height_scale"] > 0
    assert payload["build_scale"] > 0
    assert payload["bone_scales"]
    assert payload["blend_shapes"]
    assert payload["material_parameters"]
    assert payload["material_parameters"]["primary_color_id"]
    assert payload["material_parameters"]["secondary_color_id"]
    assert payload["material_parameters"]["pattern_layout_id"]
    assert payload["material_parameters"]["marking_id"]
    assert payload["material_parameters"]["region_0_id"]
    assert "region_0_source_mid_luma" in payload["material_parameters"]
    assert "region_0_intensity" in payload["material_parameters"]
    assert payload["species_traits"]
