from elfie.body.native import BipedAnatomy, GaitEngine
from infrastructure.godot import NativeBody


def test_native_body_is_the_canonical_anatomy_and_gait_api() -> None:
    assert BipedAnatomy.__module__ == "elfie.body.native.anatomy.biped"
    assert GaitEngine.__module__ == "elfie.body.native.gait"
    assert NativeBody.__module__ == "infrastructure.godot.native_body"
