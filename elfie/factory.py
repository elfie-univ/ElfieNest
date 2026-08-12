"""完整精灵的创建、恢复和依赖装配入口。"""

from __future__ import annotations

from dataclasses import dataclass

from elfie.body.port import BodyPort
from elfie.brain.activity import ActivityStorePort
from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.brain.runtime_port import ModelPort
from elfie.brain.skills import SkillManager
from elfie.brain.tool_port import ToolPort
from elfie.communication import CommunicationHub
from elfie.elfie import Elfie
from elfie.profile import ElfieProfile


@dataclass(frozen=True)
class ElfieAssembly:
    """Immutable, already-scoped dependencies for one complete Elfie."""

    profile: ElfieProfile
    memory_store: MemoryStorePort
    body: BodyPort | None = None
    bodies: tuple[BodyPort, ...] = ()
    current_body_id: str | None = None
    communication: CommunicationHub | None = None
    skills: SkillManager | None = None
    model_port: ModelPort | None = None
    tool_port: ToolPort | None = None
    activity_store: ActivityStorePort | None = None


class ElfieFactory:
    """装配现有子系统，不重新实现任何脑、身体或记忆算法。"""

    def create(self, assembly: ElfieAssembly) -> Elfie:
        """Create one Elfie from an already resolved typed assembly."""
        return self.assemble(assembly)

    def restore(self, assembly: ElfieAssembly) -> Elfie:
        """Restore one Elfie from an already loaded profile and memory store."""
        return self.assemble(assembly)

    def assemble(self, assembly: ElfieAssembly) -> Elfie:
        """Build one complete, not-yet-started Elfie from typed dependencies."""
        assembly.profile.validate()
        elfie = Elfie(
            character_profile=assembly.profile,
            memory_store=assembly.memory_store,
            body=assembly.body,
            communication=assembly.communication,
            skills=assembly.skills,
            model_port=assembly.model_port,
            tool_port=assembly.tool_port,
            activity_store=assembly.activity_store,
        )
        for available_body in assembly.bodies:
            if elfie.body_registry.get(available_body.body_id) is available_body:
                continue
            elfie.register_body(available_body)
        if assembly.body is not None and assembly.current_body_id is None:
            elfie.bind_body(assembly.body.body_id)
        if assembly.current_body_id is not None:
            elfie.bind_body(assembly.current_body_id)
        return elfie
