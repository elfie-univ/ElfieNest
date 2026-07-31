from __future__ import annotations

from pathlib import Path

import pytest

import devtools.elfie_lab.session_registry as session_registry_module
from devtools.elfie_lab.session_registry import SessionRegistry
from devtools.elfie_lab.storage import ElfieLabStorage


def _create_storage(tmp_path: Path) -> tuple[ElfieLabStorage, str]:
    storage = ElfieLabStorage(str(tmp_path / "data"))
    spec = storage.create_elfie(
        "会话事务测试",
        description="验证人格更新事务",
        personality_description="温柔安静",
        appearance_description="浅色毛发",
    )
    return storage, spec.elfie_id


def test_reload_keeps_existing_session_when_update_fails(tmp_path: Path) -> None:
    # Given
    storage, elfie_id = _create_storage(tmp_path)
    registry = SessionRegistry(storage, str(tmp_path / "runtime"))
    existing = registry.get(elfie_id)

    def fail_update():
        raise OSError("injected update failure")

    # When
    with pytest.raises(OSError, match="injected update failure"):
        registry.reload(elfie_id, fail_update)

    # Then
    assert registry.get(elfie_id) is existing
    assert existing._closed is False
    registry.close()


def test_reload_rolls_back_profile_when_rebuild_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Given
    storage, elfie_id = _create_storage(tmp_path)
    registry = SessionRegistry(storage, str(tmp_path / "runtime"))
    existing = registry.get(elfie_id)
    profile_path = storage.elfie_dir(elfie_id) / "profile" / "profile.yaml"
    original_profile = profile_path.read_bytes()

    def fail_rebuild(*_args, **_kwargs):
        raise RuntimeError("injected rebuild failure")

    monkeypatch.setattr(session_registry_module, "ElfieLabSession", fail_rebuild)

    # When
    with pytest.raises(RuntimeError, match="injected rebuild failure"):
        registry.reload(
            elfie_id,
            lambda: storage.update_big_five(
                elfie_id,
                {
                    "openness": 0.1,
                    "conscientiousness": 0.2,
                    "extraversion": 0.3,
                    "agreeableness": 0.4,
                    "neuroticism": 0.5,
                },
            ),
        )

    # Then
    assert registry.get(elfie_id) is existing
    assert existing._closed is False
    assert profile_path.read_bytes() == original_profile
    registry.close()
