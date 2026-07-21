"""Elfie 可替换身体及当前 Native 身体的公共导出。"""

from elfie.body.binding import BodyBinding, BodySwitchError
from elfie.body.capabilities import BodyCapabilities
from elfie.body.external import ExternalBody, ExternalTransport
from elfie.body.headless import HeadlessBody
from elfie.body.native import GodotGateway, GodotTransport, NativeBody
from elfie.body.native.anatomy.base import JointLimit, SomaticAnatomy, VoiceProfile
from elfie.body.native.anatomy.biped import BipedAnatomy
from elfie.body.native.anatomy.quadruped import QuadrupedAnatomy
from elfie.body.native.gait import GaitEngine
from elfie.body.port import ActuatorPort, BodyPort, LegacyBodyPort, SensorPort
from elfie.body.registry import (
    BodyNotFoundError,
    BodyRegistrationError,
    BodyRegistry,
)
from elfie.body.types import (
    BodyCommand,
    BodyDescriptor,
    BodyEvent,
    BodyId,
    BodyMode,
    BodySensorEvent,
    BodySnapshot,
    BodyState,
    CommandReceipt,
    CommandResult,
    CommandStatus,
    EmergencyStopCommand,
    EnvironmentSample,
    ExpressionCommand,
    LegacyBodyCommand,
    LegacyBodyEvent,
    LegacyCommandResult,
    LegacyCommandStatus,
    MotionCommand,
    ProprioceptionSample,
    ReceiptStatus,
    SpeechCommand,
    TactileImpact,
    TypedBodyCommand,
    UtteranceFinal,
    VisionChange,
    VisionSample,
)
from elfie.nervous_system.reflex.reflex_arc import SomaticReflexArc

__all__ = [
    "SomaticAnatomy",
    "VoiceProfile",
    "JointLimit",
    "BipedAnatomy",
    "QuadrupedAnatomy",
    "GaitEngine",
    "SomaticReflexArc",
    "SensorPort",
    "ActuatorPort",
    "BodyPort",
    "LegacyBodyPort",
    "BodyCapabilities",
    "BodyRegistry",
    "BodyRegistrationError",
    "BodyNotFoundError",
    "BodyBinding",
    "BodySwitchError",
    "BodyEvent",
    "BodyCommand",
    "CommandResult",
    "CommandStatus",
    "BodyDescriptor",
    "BodyState",
    "BodyMode",
    "HeadlessBody",
    "GodotGateway",
    "GodotTransport",
    "NativeBody",
    "ExternalTransport",
    "ExternalBody",
    "BodyId",
    "BodySensorEvent",
    "BodySnapshot",
    "CommandReceipt",
    "ReceiptStatus",
    "TypedBodyCommand",
    "SpeechCommand",
    "MotionCommand",
    "ExpressionCommand",
    "EmergencyStopCommand",
    "UtteranceFinal",
    "VisionSample",
    "VisionChange",
    "TactileImpact",
    "ProprioceptionSample",
    "EnvironmentSample",
    "LegacyBodyEvent",
    "LegacyBodyCommand",
    "LegacyCommandResult",
    "LegacyCommandStatus",
]
