from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from elfie.body.native.anatomy.base import SomaticAnatomy, VoiceProfile
from elfie.body.port import BodyPort
from elfie.body.types import BodyCommand, BodyEvent, CommandResult
from elfie.nervous_system.actuators import (
    MotionActuator,
    MutterActuator,
    SpeechActuator,
)
from elfie.nervous_system.physical_limits import PhysicalLimitsReflex
from elfie.nervous_system.reflex import SomaticReflexArc
from elfie.nervous_system.sensors import AudioSensor, EnvironmentSensor, VisionSensor
from elfie.nervous_system.signal_filter import SensoryDamSignalFilter


class NervousSystem:
    """统一大脑与身体之间的感知、反射、校验和动作传递入口。"""

    def __init__(self, capabilities_config: Optional[Dict[str, Any]] = None):
        self.vision_sensor = VisionSensor()
        self.audio_sensor = AudioSensor()
        self.environment_sensor = EnvironmentSensor()

        self.speech_actuator = SpeechActuator()
        self.motion_actuator = MotionActuator()
        self.mutter_actuator = MutterActuator()

        self.signal_filter = SensoryDamSignalFilter()
        self.physical_limits = PhysicalLimitsReflex(capabilities_config)
        self.reflex = SomaticReflexArc()

    def receive(self, events: Iterable[BodyEvent]) -> Dict[str, Any]:
        """把当前身体的一批事件归并为现有认知链使用的感知数据。

        Body 负责把具体来源适配成 ``BodyEvent``；神经系统在这里按感官类别
        接收并保留事件顺序。返回值暂时维持旧认知链的字典结构，避免重写大脑。
        """
        raw_sensor_data: Dict[str, Any] = {"sensory_events": []}
        heard_messages: List[str] = []
        image_paths: List[str] = []

        for event in events:
            payload = dict(event.payload)
            raw_sensor_data["sensory_events"].append(
                {
                    "event_id": event.event_id,
                    "sensor": event.sensor,
                    "source": event.source,
                    "timestamp": event.timestamp,
                    "payload": payload,
                }
            )

            if event.sensor == "hearing":
                heard = str(
                    payload.get("user_message")
                    or payload.get("transcript")
                    or payload.get("text")
                    or ""
                ).strip()
                if heard:
                    heard_messages.append(
                        self.audio_sensor.receive_virtual_audio(heard, event.source)
                    )
            elif event.sensor == "vision":
                candidates = payload.get("images", payload.get("image_paths", ()))
                if isinstance(candidates, str):
                    candidates = (candidates,)
                image_paths.extend(str(path) for path in candidates if str(path))
                single_path = payload.get("image") or payload.get("path")
                if single_path:
                    image_paths.append(str(single_path))
            elif event.sensor == "touch":
                self.environment_sensor.receive_tactile_pulse(
                    impact_force=float(payload.get("impact_force", 0.0)),
                    direction=str(payload.get("impact_direction", "none")),
                    stroke_freq=float(payload.get("gentle_stroke", 0.0)),
                )
            elif event.sensor == "environment":
                self.environment_sensor.update_from_godot_world(payload)

            # 旧认知链仍读取扁平字段；同名字段以最新事件为准，完整事件不会丢失。
            raw_sensor_data.update(payload)

        if heard_messages:
            raw_sensor_data["has_new_message"] = True
            raw_sensor_data["user_message"] = "\n".join(heard_messages)
        if image_paths:
            raw_sensor_data["images"] = list(dict.fromkeys(image_paths))

        return raw_sensor_data

    def control(self, body: BodyPort, command: BodyCommand) -> CommandResult:
        """把已校验的语义动作交给当前身体执行。

        神经系统不判断 Godot 动画、电机或无界面记录的实现细节；对应身体根据
        自身 capabilities 决定执行或拒绝，并返回统一结果。
        """
        return body.execute(command)

    def filter_signals(self, raw_sensor_data: Dict[str, Any]) -> bool:
        """过滤重复或无价值的感知信号。"""
        return self.signal_filter.filter_noise(raw_sensor_data)

    def process_reflex(
        self,
        anatomy: SomaticAnatomy,
        tactile_sensor: Dict[str, Any],
        emotion_system: Any,
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """处理可绕过认知层的即时身体反射。"""
        return self.reflex.process_sensory_impact(
            anatomy=anatomy,
            tactile_sensor=tactile_sensor,
            amygdala=emotion_system,
        )

    def validate_action(
        self, action_name: str, anatomy: SomaticAnatomy
    ) -> Dict[str, Any]:
        """根据当前身体形态校验动作是否能够执行。"""
        return self.physical_limits.intercept_and_validate(action_name, anatomy)

    def speak(self, text: str, voice_profile: Optional[VoiceProfile] = None) -> str:
        """把说话意图交给发声执行器。"""
        return self.speech_actuator.synthesize_speech(text, voice_profile)

    def drive(
        self,
        anatomy: SomaticAnatomy,
        action: str,
        speed: float = 1.0,
        elapsed_time: float = 0.0,
    ) -> Dict[str, float]:
        """把高阶动作意图转换为当前身体的关节驱动。"""
        return self.motion_actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent=action,
            speed=speed,
            elapsed_time=elapsed_time,
        )

    def mutter(self, status: str) -> str:
        """把内部状态转换为精灵的碎碎念。"""
        return self.mutter_actuator.mutter(status)
