"""
Elfie Body Physical Somatic Layer
物理躯体躯壳层：声明 3D 骨架、物理极限、声音曲线与小脑步态步频，及脑干自律快速反射弧。
"""

from elfie.body.actuators.gait import GaitEngine
from elfie.body.anatomy.base import JointLimit, SomaticAnatomy, VoiceProfile
from elfie.body.anatomy.biped import BipedAnatomy
from elfie.body.anatomy.quadruped import QuadrupedAnatomy
from elfie.body.reflex.reflex_arc import SomaticReflexArc

__all__ = [
    "SomaticAnatomy",
    "VoiceProfile",
    "JointLimit",
    "BipedAnatomy",
    "QuadrupedAnatomy",
    "GaitEngine",
    "SomaticReflexArc",
]
