"""Elfie 可替换身体语义与端口的公共导出。"""

from elfie.body.binding import BodyBinding, BodySwitchError
from elfie.body.capabilities import BodyCapabilities
from elfie.body.contracts import (
    ActionOutcomePayload,
    BodyCommand,
    BodyId,
    BodySensorEvent,
    BodySnapshot,
    CapabilityCommand,
    CommandReceipt,
    CommandStatus,
    EmergencyStopCommand,
    EnvironmentSample,
    ExpressionCommand,
    HeardUtterancePayload,
    MotionCommand,
    NestFactNoticePayload,
    ObservationCommand,
    ProprioceptionSample,
    SemanticActionResultPayload,
    SemanticVisualEntityPayload,
    SemanticVisualScenePayload,
    SpeechCommand,
    TactileImpact,
    UtteranceFinal,
    VisionChange,
    VisionSample,
)
from elfie.body.headless import HeadlessBody
from elfie.body.native.anatomy.base import JointLimit, SomaticAnatomy, VoiceProfile
from elfie.body.native.anatomy.biped import BipedAnatomy
from elfie.body.native.anatomy.quadruped import QuadrupedAnatomy
from elfie.body.native.gait import GaitEngine
from elfie.body.port import ActuatorPort, BodyPort, SensorPort
from elfie.body.registry import (
    BodyNotFoundError,
    BodyRegistrationError,
    BodyRegistry,
)
from elfie.body.types import (
    BodyDescriptor,
    BodyMode,
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
    "BodyCapabilities",
    "BodyRegistry",
    "BodyRegistrationError",
    "BodyNotFoundError",
    "BodyBinding",
    "BodySwitchError",
    "BodyCommand",
    "ActionOutcomePayload",
    "CommandStatus",
    "BodyDescriptor",
    "BodyMode",
    "HeadlessBody",
    "BodyId",
    "BodySensorEvent",
    "BodySnapshot",
    "CapabilityCommand",
    "CommandReceipt",
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
    "HeardUtterancePayload",
    "NestFactNoticePayload",
    "ObservationCommand",
    "SemanticActionResultPayload",
    "SemanticVisualEntityPayload",
    "SemanticVisualScenePayload",
]
