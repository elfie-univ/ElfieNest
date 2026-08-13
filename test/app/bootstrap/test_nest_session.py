"""Nest Session composition owns persisted Elfie construction."""

from pathlib import Path
from types import SimpleNamespace

from app.bootstrap.system_wiring import nest_session as nest_session_bootstrap


class _FakeFactory:
    def restore(self, assembly: object) -> object:
        if assembly.body.body_id == "broken":
            raise ValueError("invalid profile")
        return (assembly, assembly.body, assembly.profile.identity.elfie_id)


class _FakeSession:
    world_runtime = object()

    def __init__(self) -> None:
        self.registered: list[tuple[str, object]] = []

    def register_elfie(self, elfie_id: str, elfie: object) -> None:
        self.registered.append((elfie_id, elfie))


def test_restore_registered_elfies_isolates_one_invalid_profile(monkeypatch) -> None:
    rows = (
        SimpleNamespace(elfie_id="ready", name="Ready"),
        SimpleNamespace(elfie_id="broken", name="Broken"),
    )
    monkeypatch.setattr(nest_session_bootstrap, "ElfieFactory", _FakeFactory)
    monkeypatch.setattr(
        nest_session_bootstrap,
        "SQLiteElfiesProjectionAdapter",
        lambda _db_path: SimpleNamespace(list_directory=lambda: rows),
    )
    monkeypatch.setattr(
        nest_session_bootstrap,
        "get_elfie_config_dir",
        lambda elfie_id: f"/profiles/{elfie_id}",
    )

    def profile_store(path):
        elfie_id = Path(path).parent.name
        return SimpleNamespace(
            load=lambda: SimpleNamespace(
                identity=SimpleNamespace(elfie_id=elfie_id),
                validate=lambda: None,
                personality={},
                species_id="fox",
            )
        )

    monkeypatch.setattr(
        nest_session_bootstrap, "YamlProfileStoreAdapter", profile_store
    )
    monkeypatch.setattr(
        nest_session_bootstrap,
        "SQLiteMemoryStoreAdapter",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        nest_session_bootstrap,
        "SQLiteActivityStoreAdapter",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        nest_session_bootstrap,
        "SQLiteBrainJournalAdapter",
        lambda _path: object(),
    )
    session = _FakeSession()

    result = nest_session_bootstrap.restore_registered_elfies(
        "/tmp/nest.db",
        session,  # type: ignore[arg-type]
    )

    assert result.restored == (nest_session_bootstrap.RestoredElfie("ready", "Ready"),)
    assert result.failures == (
        nest_session_bootstrap.ElfieRestoreFailure(
            "broken",
            "Broken",
            "invalid profile",
        ),
    )
    assert len(session.registered) == 1
    registered_id, restored = session.registered[0]
    assert registered_id == "ready"
    assert restored[0].profile.identity.elfie_id == "ready"
    assert restored[1].body_id == "ready"
    assert restored[2] == "ready"
