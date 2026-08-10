from __future__ import annotations

import urllib.error
from unittest.mock import Mock

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from app.features.operations import OperationsFacade, UsageStatsResult
from app.interfaces.cli.tui import config_views


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
    monkeypatch.setattr(
        config_views.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            urllib.error.URLError("offline")
        ),
    )
    monkeypatch.setattr(config_views, "read_user_config", lambda: {})
    monkeypatch.setattr(config_views, "_pause", lambda: None)

    config_views.test_config({}, operations)

    assert "Database OK (2 users)" in capsys.readouterr().out
    operations.get_usage_stats.assert_called_once()
