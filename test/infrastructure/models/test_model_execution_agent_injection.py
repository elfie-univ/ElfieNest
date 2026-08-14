from __future__ import annotations

import pytest

from infrastructure.models.model_execution_agent import ModelExecutionAgent
from infrastructure.models.model_execution_config import ModelExecutionConfig
from test.support.model_execution_agent import model_execution_agent_ports


def test_runtime_food_loading_requires_an_explicit_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    agent = ModelExecutionAgent(
        ModelExecutionConfig(), ports=model_execution_agent_ports()
    )

    with pytest.raises(RuntimeError, match="粮食数据库仓储"):
        agent._load_food_catalog()
