from infrastructure.godot import NativeBody


def test_native_body_is_the_canonical_godot_body_port_api() -> None:
    assert NativeBody.__module__ == "infrastructure.godot.native_body"
