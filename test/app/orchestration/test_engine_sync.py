from types import SimpleNamespace

from app.orchestration.engine import ElfieNestEngine
from elfie.profile import create_visual_profile


def test_godot_sync_payload_includes_render_appearance() -> None:
    elfie = SimpleNamespace(
        brain=SimpleNamespace(
            profile=SimpleNamespace(
                personality={
                    "metadata": {
                        "name": "小栗",
                        "appearance": {
                            "species": "fox",
                            "height": "short",
                            "build": "plump",
                        },
                    }
                }
            )
        )
    )

    assert ElfieNestEngine._build_godot_elfie_payload("elfie_1", elfie) == {
        "elfie_id": "elfie_1",
        "name": "小栗",
        "species": "fox",
        "height": "short",
        "build": "plump",
    }


def test_godot_sync_payload_uses_identity_without_profile() -> None:
    assert ElfieNestEngine._build_godot_elfie_payload(
        "elfie_2", SimpleNamespace()
    ) == {"elfie_id": "elfie_2", "name": "elfie_2"}


def test_godot_sync_uses_stable_character_profile_as_primary_source() -> None:
    profile = create_visual_profile(
        elfie_id="elfie_3",
        display_name="阿福",
        species_id="dog",
        seed=77,
        height_direction="tall",
        build_direction="plump",
    )

    payload = ElfieNestEngine._build_godot_elfie_payload(
        "elfie_3", SimpleNamespace(character_profile=profile)
    )

    assert payload["elfie_id"] == "elfie_3"
    assert payload["name"] == "阿福"
    assert payload["species"] == "dog"
    assert payload["appearance"]["species_id"] == "dog"
    assert payload["appearance"]["bone_scales"]
    assert payload["appearance"]["blend_shapes"]
    assert payload["appearance"]["material_parameters"]
