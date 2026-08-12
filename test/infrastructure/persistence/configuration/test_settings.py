from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.features.configuration.settings import (
    SettingsStorageError,
    StoredRuntimeSettings,
    StoredSecuritySettings,
)
from infrastructure.persistence.configuration.settings import RuntimeSettingsAdapter


def _runtime_path(root: Path) -> Path:
    return root / "configs" / "runtime.yaml"


def test_defaults_are_returned_without_creating_a_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    adapter = RuntimeSettingsAdapter()

    assert adapter.load_elfie_settings().max_elfies_per_user == 3
    assert adapter.load_runtime_settings().tick_interval_sec == 1.5
    assert adapter.load_security_settings().session_ttl_days == 7
    assert not _runtime_path(tmp_path).exists()


def test_section_update_preserves_unowned_runtime_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    path = _runtime_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "system": {"security": {"session_ttl_days": 4}},
                "runtime_policy": {"unowned": {"enabled": True}},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    RuntimeSettingsAdapter().save_runtime_settings(
        StoredRuntimeSettings(tick_interval_sec=2.0)
    )

    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["system"]["engine"] == {"tick_interval_sec": 2.0}
    assert saved["system"]["security"] == {"session_ttl_days": 4}
    assert saved["runtime_policy"]["unowned"] == {"enabled": True}


def test_corrupt_owned_section_is_not_silently_coerced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    path = _runtime_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        "version: 1\nsystem:\n  engine:\n    tick_interval_sec: fast\n",
        encoding="utf-8",
    )

    with pytest.raises(SettingsStorageError, match="tick_interval_sec"):
        RuntimeSettingsAdapter().load_runtime_settings()


def test_security_write_is_a_complete_typed_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    RuntimeSettingsAdapter().save_security_settings(
        StoredSecuritySettings(
            session_ttl_days=2,
            rate_limit=RuntimeSettingsAdapter().load_security_settings().rate_limit,
        )
    )

    saved = yaml.safe_load(_runtime_path(tmp_path).read_text(encoding="utf-8"))
    assert saved["system"]["security"] == {
        "session_ttl_days": 2,
        "rate_limit": {"max_attempts": 5, "window_seconds": 300},
    }


def test_reset_settings_preserves_unowned_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    path = _runtime_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "system": {"engine": {"tick_interval_sec": 9.0}},
                "runtime_policy": {"unowned": {"enabled": True}},
            }
        ),
        encoding="utf-8",
    )

    RuntimeSettingsAdapter().reset_settings()

    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["system"]["engine"]["tick_interval_sec"] == 1.5
    assert saved["runtime_policy"]["unowned"]["enabled"] is True
