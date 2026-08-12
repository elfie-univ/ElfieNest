from __future__ import annotations

import pytest

from infrastructure.models.runtime_agent import RuntimeAgent
from infrastructure.models.runtime_config import LLMRuntimeConfig
from test.support.runtime_agent import runtime_agent_ports


def test_runtime_food_loading_requires_an_explicit_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    agent = RuntimeAgent(LLMRuntimeConfig(), ports=runtime_agent_ports())

    with pytest.raises(RuntimeError, match="粮食数据库仓储"):
        agent._load_food_catalog()
