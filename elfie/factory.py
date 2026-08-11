"""完整精灵的创建、恢复和依赖装配入口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Union

from elfie.body.port import BodyPort
from elfie.brain.memory import MemoryStorePort
from elfie.brain.runtime_port import ModelPort
from elfie.brain.skills import SkillManager
from elfie.communication import CommunicationHub
from elfie.elfie import Elfie
from elfie.profile import ElfieProfile, ProfileStorePort

ConfigPath = Union[str, Path]


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


class ElfieFactory:
    """装配现有子系统，不重新实现任何脑、身体或记忆算法。"""

    def create(
        self,
        *,
        config_dir: Optional[ConfigPath] = None,
        elfie_id: Optional[str] = None,
        memory_db_path: Optional[str] = None,
        memory_store: Optional[MemoryStorePort] = None,
        character_profile: Optional[ElfieProfile] = None,
        body: Optional[BodyPort] = None,
        bodies: Iterable[BodyPort] = (),
        current_body_id: Optional[str] = None,
        communication: Optional[CommunicationHub] = None,
        skills: Optional[SkillManager] = None,
        model_port: Optional[ModelPort] = None,
        profile_store: Optional[ProfileStorePort] = None,
    ) -> Elfie:
        normalized_config_dir = str(config_dir) if config_dir is not None else None
        profile = self._resolve_profile(
            normalized_config_dir,
            character_profile,
            elfie_id,
            profile_store,
        )
        resolved_elfie_id = self._resolve_elfie_id(elfie_id, profile)

        if memory_store is not None:
            if profile is None:
                from elfie.initialization import assemble_profile  # noqa: PLC0415

                profile = assemble_profile(
                    config_dir=None,
                    elfie_id=resolved_elfie_id,
                    supplied=None,
                )
            return self.assemble(
                ElfieAssembly(
                    profile=profile,
                    memory_store=memory_store,
                    body=body,
                    bodies=tuple(bodies),
                    current_body_id=current_body_id,
                    communication=communication,
                    skills=skills,
                    model_port=model_port,
                )
            )

        elfie = Elfie(
            config_dir=normalized_config_dir,
            elfie_id=resolved_elfie_id,
            memory_db_path=memory_db_path,
            character_profile=profile,
            body=body,
            communication=communication,
            skills=skills,
            model_port=model_port,
            profile_store=profile_store,
        )
        for available_body in bodies:
            if elfie.body_registry.get(available_body.body_id) is available_body:
                continue
            elfie.register_body(available_body)
        if body is not None and current_body_id is None:
            elfie.bind_body(body.body_id)
        if current_body_id is not None:
            elfie.bind_body(current_body_id)
        return elfie

    def restore(
        self,
        config_dir: ConfigPath,
        *,
        elfie_id: Optional[str] = None,
        memory_db_path: Optional[str] = None,
        memory_store: Optional[MemoryStorePort] = None,
        body: Optional[BodyPort] = None,
        bodies: Iterable[BodyPort] = (),
        current_body_id: Optional[str] = None,
        communication: Optional[CommunicationHub] = None,
        skills: Optional[SkillManager] = None,
        model_port: Optional[ModelPort] = None,
        profile_store: Optional[ProfileStorePort] = None,
    ) -> Elfie:
        """Restore one Elfie from its final workspace."""
        if profile_store is None or not profile_store.exists():
            raise FileNotFoundError("精灵最终档案不存在")
        elfie = self.create(
            config_dir=config_dir,
            elfie_id=elfie_id,
            memory_db_path=memory_db_path,
            body=body,
            bodies=bodies,
            current_body_id=current_body_id,
            communication=communication,
            skills=skills,
            model_port=model_port,
            profile_store=profile_store,
            memory_store=memory_store,
        )
        return elfie

    def assemble(self, assembly: ElfieAssembly) -> Elfie:
        """Build one complete, not-yet-started Elfie from typed dependencies."""
        assembly.profile.validate()
        elfie = Elfie(
            elfie_id=assembly.profile.identity.elfie_id,
            character_profile=assembly.profile,
            memory_store=assembly.memory_store,
            body=assembly.body,
            communication=assembly.communication,
            skills=assembly.skills,
            model_port=assembly.model_port,
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

    @staticmethod
    def _resolve_profile(
        config_dir: Optional[str],
        supplied: Optional[ElfieProfile],
        elfie_id: Optional[str],
        profile_store: Optional[ProfileStorePort],
    ) -> Optional[ElfieProfile]:
        if supplied is not None:
            supplied.validate()
            return supplied
        if config_dir is None:
            return None
        if profile_store is not None and profile_store.exists():
            return profile_store.load()
        if profile_store is None:
            raise ValueError("config_dir 创建 Elfie 时必须注入 profile_store")
        from elfie.initialization import assemble_profile  # noqa: PLC0415

        profile = assemble_profile(config_dir=None, elfie_id=elfie_id, supplied=None)
        profile_store.save(profile)
        return profile

    @staticmethod
    def _resolve_elfie_id(
        supplied_id: Optional[str], profile: Optional[ElfieProfile]
    ) -> Optional[str]:
        if profile is None:
            return supplied_id
        profile_id = profile.identity.elfie_id
        if supplied_id is not None and supplied_id != profile_id:
            raise ValueError(
                f"elfie_id={supplied_id!r} 与 profile 身份 {profile_id!r} 不一致"
            )
        return profile_id
