from elfie.nervous_system import NervousSystem


def test_nervous_system_is_the_canonical_sensor_and_actuator_api() -> None:
    assert NervousSystem.__module__ == "elfie.nervous_system.nervous_system"
