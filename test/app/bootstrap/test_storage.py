"""Application storage initialization is selected only by Bootstrap."""

from app.bootstrap.app_wiring import storage


def test_memory_storage_does_not_run_file_schema_initializer(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(storage, "init_db", calls.append)

    storage.ensure_application_storage(":memory:")

    assert calls == []


def test_application_storage_has_one_schema_initialization_entry(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(storage, "init_db", calls.append)

    storage.ensure_application_storage("/tmp/nest.db")

    assert calls == ["/tmp/nest.db"]
