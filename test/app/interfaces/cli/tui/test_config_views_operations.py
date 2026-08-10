from __future__ import annotations

from unittest.mock import Mock

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from app.features.operations import OperationsFacade, UsageStatsResult
from app.interfaces.cli.tui import config_views
from test.app.interfaces.cli.configuration_test_support import (
    FakeProvidersService,
    manager_principal,
    settings_service,
)


def test_config_check_reads_database_through_operations_facade(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    operations = Mock(spec=OperationsFacade)
    operations.get_usage_stats.return_value = UsageStatsResult(
        user_count=2,
        owner_count=1,
        elfie_count=1,
        session_count=0,
        species_stats=(),
    )
    monkeypatch.setattr(config_views, "_pause", lambda: None)

    config_views.test_config(
        FakeProvidersService(),
        settings_service(),
        operations,
        manager_principal(),
    )

    assert "Database OK (2 users)" in capsys.readouterr().out
    operations.get_usage_stats.assert_called_once()
