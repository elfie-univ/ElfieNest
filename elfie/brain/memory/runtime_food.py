"""记忆子系统调用 Runtime 的粮食语义边界。"""

from __future__ import annotations

from typing import Any


def ask_memory_model(
    runtime_agent: Any,
    prompt: str,
    *,
    elfie_id: str | None,
    config_dir: str | None,
    semantic_role: str,
    complexity: int,
) -> str:
    ask_with_food = getattr(runtime_agent, "ask_with_food", None)
    if callable(ask_with_food):
        return ask_with_food(
            prompt=prompt,
            food_key=None,
            semantic_role=semantic_role,
            elfie_id=elfie_id,
            elfie_config_dir=config_dir,
            scene="memory",
            energy=50.0,
            task_complexity=complexity,
            allowed_skills=[],
        )
    # 测试 Mock 和旧第三方 Runtime 的兼容边界。
    return runtime_agent.ask(
        prompt,
        energy=50.0,
        task_complexity=complexity,
    )
