"""完整精灵的创建、恢复和依赖装配入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional, Union

from elfie.body.native import GodotTransport, NativeBody
from elfie.body.port import BodyPort
from elfie.communication import CommunicationHub
from elfie.elfie import Elfie
from elfie.profile import ElfieProfile, ElfieProfileRepository
from elfie.skills import SkillManager
from elfie.state import ElfieStateRepository

ConfigPath = Union[str, Path]


class ElfieFactory:
    """装配现有子系统，不重新实现任何脑、身体或记忆算法。"""

    def create(
        self,
        *,
        config_dir: Optional[ConfigPath] = None,
        anatomy_type: Optional[str] = None,
        godot_api: Any = None,
        elfie_id: Optional[str] = None,
        memory_db_path: Optional[str] = None,
        character_profile: Optional[ElfieProfile] = None,
        body: Optional[BodyPort] = None,
        bodies: Iterable[BodyPort] = (),
        current_body_id: Optional[str] = None,
        communication: Optional[CommunicationHub] = None,
        skills: Optional[SkillManager] = None,
    ) -> Elfie:
        normalized_config_dir = str(config_dir) if config_dir is not None else None
        profile = self._resolve_profile(normalized_config_dir, character_profile)
        resolved_elfie_id = self._resolve_elfie_id(elfie_id, profile)
        auto_native_body = body is None and godot_api is not None
        if auto_native_body:
            body = NativeBody(
                body_id=resolved_elfie_id or "elfie_default",
                transport=GodotTransport(godot_api),
            )

        elfie = Elfie(
            config_dir=normalized_config_dir,
            anatomy_type=anatomy_type,
            elfie_id=resolved_elfie_id,
            memory_db_path=memory_db_path,
            character_profile=profile,
            body=body,
            communication=communication,
            skills=skills,
        )
        for available_body in bodies:
            if elfie.body_registry.get(available_body.body_id) is available_body:
                continue
            elfie.register_body(available_body)
        if auto_native_body and body is not None:
            elfie.bind_body(body.body_id)
        if current_body_id is not None:
            elfie.bind_body(current_body_id)
        return elfie

    def restore(
        self,
        config_dir: ConfigPath,
        *,
        anatomy_type: Optional[str] = None,
        godot_api: Any = None,
        elfie_id: Optional[str] = None,
        memory_db_path: Optional[str] = None,
        body: Optional[BodyPort] = None,
        bodies: Iterable[BodyPort] = (),
        current_body_id: Optional[str] = None,
        communication: Optional[CommunicationHub] = None,
        skills: Optional[SkillManager] = None,
    ) -> Elfie:
        """从已有目录恢复；旧目录没有 profile.yaml 时沿用原兼容加载逻辑。"""
        path = Path(config_dir).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"精灵配置目录不存在: {path}")
        profile_repository = ElfieProfileRepository(path)
        had_profile = profile_repository.exists()
        elfie = self.create(
            config_dir=path,
            anatomy_type=anatomy_type,
            godot_api=godot_api,
            elfie_id=elfie_id,
            memory_db_path=memory_db_path,
            body=body,
            bodies=bodies,
            current_body_id=current_body_id,
            communication=communication,
            skills=skills,
        )
        if not had_profile:
            profile_repository.save(elfie.profile)
        state_repository = ElfieStateRepository(path)
        if state_repository.exists():
            # 显式传入的身体选择优先于持久状态。
            restore_body = body is None and current_body_id is None
            elfie.restore_state(
                state_repository.load(),
                restore_body=restore_body,
            )
        return elfie

    @staticmethod
    def _resolve_profile(
        config_dir: Optional[str], supplied: Optional[ElfieProfile]
    ) -> Optional[ElfieProfile]:
        if supplied is not None:
            supplied.validate()
            return supplied
        if config_dir is None:
            return None
        repository = ElfieProfileRepository(config_dir)
        return repository.load() if repository.exists() else None

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
