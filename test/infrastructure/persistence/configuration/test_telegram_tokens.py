from __future__ import annotations

import stat
from pathlib import Path

from infrastructure.persistence.configuration.secrets import write_secrets
from infrastructure.persistence.configuration.telegram_tokens import (
    TelegramTokenAdapter,
)


def test_telegram_token_is_isolated_in_auth_env_and_can_be_revoked(
    tmp_path: Path,
) -> None:
    path = tmp_path / "configs" / "auth.env"
    write_secrets({"KEEP_ME": "other-secret"}, path)
    tokens = TelegramTokenAdapter(path)

    reference = tokens.replace("00000001", "991:telegram-secret")

    assert reference == "ELFIE_TELEGRAM_00000001_BOT_TOKEN"
    assert tokens.load(reference) == "991:telegram-secret"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    tokens.delete("00000001")
    assert tokens.load(reference) == ""
    assert "KEEP_ME=other-secret" in path.read_text(encoding="utf-8")
