from elfie import Elfie
from elfie.body import BodyCommand, BodyEvent, CommandStatus, HeadlessBody
from elfie.body.native.anatomy.biped import BipedAnatomy
from elfie.brain.emotion import EmotionSystem
from elfie.nervous_system import NervousSystem


def test_nervous_system_owns_sensors_and_processing_components() -> None:
    nervous_system = NervousSystem()

    assert nervous_system.vision_sensor is not None
    assert nervous_system.audio_sensor is not None
    assert nervous_system.environment_sensor is not None
    assert nervous_system.speech_actuator is not None
    assert nervous_system.motion_actuator is not None
    assert nervous_system.mutter_actuator is not None
    assert nervous_system.signal_filter is not None
    assert nervous_system.physical_limits is not None
    assert nervous_system.reflex is not None


def test_elfie_owns_one_canonical_nervous_system() -> None:
    elfie = Elfie(memory_db_path=":memory:")

    assert elfie.nervous_system.speech_actuator is not None
    assert elfie.nervous_system.motion_actuator is not None
    assert elfie.nervous_system.mutter_actuator is not None
    assert elfie.nervous_system.signal_filter is not None
    assert elfie.nervous_system.physical_limits is not None
    assert elfie.nervous_system.reflex is not None


def test_nervous_system_filters_signals_through_existing_filter() -> None:
    nervous_system = NervousSystem()

    assert nervous_system.filter_signals({"temperature": 24.0}) is True
    assert nervous_system.filter_signals({"temperature": 24.0}) is False
    assert nervous_system.filter_signals({"temperature": 25.0}) is True


def test_nervous_system_receives_body_events_by_existing_sense_categories() -> None:
    nervous_system = NervousSystem()
    events = [
        BodyEvent(
            sensor="hearing",
            source="godot:user_message",
            payload={"user_message": "第一句话", "message_id": "m1"},
        ),
        BodyEvent(
            sensor="hearing",
            source="godot:user_message",
            payload={"user_message": "第二句话", "message_id": "m2"},
        ),
        BodyEvent(
            sensor="touch",
            source="godot:collision",
            payload={"impact_force": 8.0, "impact_direction": "left"},
        ),
    ]

    received = nervous_system.receive(events)

    assert received["user_message"] == "第一句话\n第二句话"
    assert received["has_new_message"] is True
    assert received["message_id"] == "m2"
    assert received["impact_force"] == 8.0
    assert [event["sensor"] for event in received["sensory_events"]] == [
        "hearing",
        "hearing",
        "touch",
    ]
    assert nervous_system.audio_sensor.get_last_heard() == "第二句话"
    assert nervous_system.environment_sensor.get_tactile_data()["impact_force"] == 8.0


def test_nervous_system_controls_current_body_through_body_port() -> None:
    nervous_system = NervousSystem()
    body = HeadlessBody(body_id="debug")
    body.connect()

    result = nervous_system.control(body, BodyCommand(action="gesture.wave"))

    assert result.status is CommandStatus.COMPLETED
    assert body.last_result is result


def test_nervous_system_processes_reflex_through_existing_reflex_arc() -> None:
    nervous_system = NervousSystem()
    anatomy = BipedAnatomy()
    emotion = EmotionSystem()

    joints, event = nervous_system.process_reflex(
        anatomy,
        {"impact_force": 20.0, "impact_direction": "front"},
        emotion,
    )

    assert event["triggered"] is True
    assert event["type"] == "shock_avoidance"
    assert joints["neck_pitch"] == 0.5


def test_nervous_system_validates_and_executes_existing_actions() -> None:
    nervous_system = NervousSystem()
    anatomy = BipedAnatomy()

    assert nervous_system.validate_action("idle", anatomy)["allowed"] is True
    assert nervous_system.validate_action("jump", anatomy)["allowed"] is False
    assert nervous_system.speak("你好", anatomy.voice_profile) == "你好"
    assert nervous_system.mutter("sleeping")

    joints = nervous_system.drive(anatomy, "nod_head", elapsed_time=1.0)
    assert joints["neck_pitch"] == 0.4
    assert joints["head_yaw"] == 0.0
