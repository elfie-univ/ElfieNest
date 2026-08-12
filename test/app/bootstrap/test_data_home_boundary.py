from __future__ import annotations

from app.bootstrap import create_app


def test_in_memory_app_composition_does_not_create_product_layout(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)

    create_app(db_path=":memory:")

    forbidden = {"assets", "configs", "elfies", "logs", "reports", "runtime"}
    assert forbidden.isdisjoint(path.name for path in tmp_path.iterdir())
