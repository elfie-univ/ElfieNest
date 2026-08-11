"""Application storage initialization is selected only by Bootstrap."""

from app.bootstrap import storage


def test_memory_storage_does_not_run_file_schema_initializer(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(storage, "init_db", calls.append)

    storage.ensure_application_storage(":memory:")

    assert calls == []


def test_service_storage_preserves_owner_seed_order(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        storage,
        "init_db",
        lambda path: calls.append(("schema", path)),
    )
    monkeypatch.setattr(
        storage,
        "seed_initial_owner_if_env_set",
        lambda path: calls.append(("owner", path)),
    )

    storage.initialize_service_storage("/tmp/nest.db")

    assert calls == [
        ("schema", "/tmp/nest.db"),
        ("owner", "/tmp/nest.db"),
    ]


def test_application_startup_storage_can_preserve_recovery_order(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        storage,
        "init_db",
        lambda path: calls.append(("schema", path)),
    )
    monkeypatch.setattr(
        storage,
        "seed_initial_owner_if_env_set",
        lambda path: calls.append(("owner", path)),
    )

    storage.initialize_application_storage("/tmp/nest.db")
    calls.append(("recover", "/tmp/nest.db"))
    storage.seed_service_owner("/tmp/nest.db")

    assert calls == [
        ("schema", "/tmp/nest.db"),
        ("recover", "/tmp/nest.db"),
        ("owner", "/tmp/nest.db"),
    ]
