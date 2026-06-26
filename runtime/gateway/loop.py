from collections.abc import Callable

from runtime.tools.executor import (
    PermissionManager,
    SandboxPlugin,
    SearchPlugin,
    SkillsEvolutionPlugin,
    ToolExecutionContext,
    ToolExecutor,
)

ToolLoopContext = ToolExecutionContext


class RuntimeToolLoop:
    def __init__(self, context: ToolLoopContext):
        self.executor = ToolExecutor(context)

    def run(
        self,
        messages: list[dict[str, str]],
        max_loops: int,
        call_llm: Callable[[list[dict[str, str]]], str],
    ) -> str:
        for _loop_idx in range(max_loops):
            response_text = call_llm(messages)
            tool_result = self.executor.execute(response_text)
            if tool_result is not None:
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": tool_result.content})
                continue

            return response_text

        raise TimeoutError(
            "❌ 算力底座在防幻觉与自进化迭代循环中超出了迭代轮数上限，请精简您的 Prompt 语境。"
        )


__all__ = [
    "PermissionManager",
    "RuntimeToolLoop",
    "SandboxPlugin",
    "SearchPlugin",
    "SkillsEvolutionPlugin",
    "ToolLoopContext",
]
