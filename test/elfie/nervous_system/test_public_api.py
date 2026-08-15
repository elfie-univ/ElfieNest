from elfie.nervous_system import MotionActuator, NervousSystem


def test_nervous_system_is_the_canonical_sensor_and_actuator_api() -> None:
    assert MotionActuator.__module__ == "elfie.nervous_system.actuators.motion"
    assert NervousSystem.__module__ == "elfie.nervous_system.nervous_system"
