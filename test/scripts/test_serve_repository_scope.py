"""Regression coverage for the service engine bootstrap scope."""

from scripts import serve


def test_engine_worker_uses_module_repository_without_uninitialized_closure() -> None:
    # Given: the service entry point defines a worker that constructs the engine.
    cell_variables = serve.main.__code__.co_cellvars

    # When: the worker resolves the repository constructor.

    # Then: the constructor is not captured as an uninitialized main-local cell.
    assert "SQLiteNestStateRepository" not in cell_variables
