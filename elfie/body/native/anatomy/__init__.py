"""Native 身体的骨架、关节和声音描述。"""

from elfie.body.native.anatomy.base import JointLimit, SomaticAnatomy, VoiceProfile
from elfie.body.native.anatomy.biped import BipedAnatomy
from elfie.body.native.anatomy.quadruped import QuadrupedAnatomy

__all__ = [
    "SomaticAnatomy",
    "VoiceProfile",
    "JointLimit",
    "BipedAnatomy",
    "QuadrupedAnatomy",
]
