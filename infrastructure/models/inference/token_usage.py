"""Token 使用追踪器 — 线程安全，按 provider + tick 累计 token 用量。"""

from __future__ import annotations

import logging
import threading
from typing import Mapping, Optional, Protocol, cast

from pydantic import JsonValue

logger = logging.getLogger("infrastructure.models.inference.token_usage")


class TokenTracker:
    """Token 使用追踪器 — 线程安全，按 provider + tick 累计 token 用量。

    数据写入 ~/.elfienest/token_usage.jsonl (JSON Lines 格式，每行一条记录)

    支持多种 API 格式：
    - OpenAI/DeepSeek: {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}
    - Anthropic: {"input_tokens": N, "output_tokens": N}
    - Ollama: {"prompt_eval_count": N, "eval_count": N}
    """

    def __init__(self, writer: TokenUsageWriter | None = None) -> None:
        self._lock = threading.Lock()
        self._writer = writer
        # {provider: {prompt_tokens, completion_tokens, total_tokens}}
        self._tick_totals: dict[str, dict[str, int]] = {}

    def record(self, provider: str, usage: Mapping[str, JsonValue]) -> None:
        """记录一次 API 调用的 token 使用量（线程安全）

        Args:
            provider: 服务商名称 (如 "ollama", "openai", "anthropic", "deepseek")
            usage: Token 使用量字典，支持多种格式：
                   - OpenAI: {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
                   - Anthropic: {"input_tokens": 100, "output_tokens": 50}
                   - Ollama: {"prompt_eval_count": 100, "eval_count": 50}
        """
        if not usage:
            return

        with self._lock:
            if provider not in self._tick_totals:
                self._tick_totals[provider] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }

            # 兼容多种命名格式
            prompt = self._token_count(
                usage.get("prompt_tokens")
                or usage.get("input_tokens")
                or usage.get("prompt_eval_count")
            )
            completion = self._token_count(
                usage.get("completion_tokens")
                or usage.get("output_tokens")
                or usage.get("eval_count")
            )
            total_value = usage.get("total_tokens")
            total = (
                self._token_count(total_value)
                if total_value is not None
                else prompt + completion
            )

            self._tick_totals[provider]["prompt_tokens"] += prompt
            self._tick_totals[provider]["completion_tokens"] += completion
            self._tick_totals[provider]["total_tokens"] += total

    def estimate_tokens(self, text: str) -> int:
        """粗略估算 token 数（1 中文字 ≈ 1.5 token，1 英文词 ≈ 1 token）

        这是一个简化的估算方法，实际 token 数可能有所不同。
        更精确的估算需要使用 tiktoken 等库。

        Args:
            text: 待估算的文本

        Returns:
            估算的 token 数
        """
        # 统计中文字符数 (CJK 基本区)
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        # 其他字符按 4 个字符 ≈ 1 token 估算
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars / 4)

    def get_tick_summary(self) -> dict[str, dict[str, int]]:
        """获取当前 tick 的累计使用量（线程安全副本）

        Returns:
            深拷贝的累计使用量字典
        """
        with self._lock:
            return {
                provider: dict(totals) for provider, totals in self._tick_totals.items()
            }

    def flush_tick(self, tick_id: str) -> None:
        """将当前 tick 数据持久化到文件，并重置计数器

        Args:
            tick_id: Tick 标识符（如时间戳或序列号）
        """
        with self._lock:
            if not self._tick_totals:
                return
            record = cast(
                Mapping[str, JsonValue],
                {"tick_id": tick_id, "usage": dict(self._tick_totals)},
            )
            self._tick_totals = {}

        if self._writer is None:
            return
        try:
            self._writer.write(record)
        except Exception as e:
            logger.warning("Token 追踪数据持久化失败: %s", e)

    def reset(self) -> None:
        """重置当前 tick 计数器（不持久化）"""
        with self._lock:
            self._tick_totals = {}

    @staticmethod
    def _token_count(value: JsonValue | None) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return max(0, int(value))
        return 0


# 全局单例
class TokenUsageWriter(Protocol):
    def write(self, record: Mapping[str, JsonValue]) -> None: ...


_token_tracker: Optional[TokenTracker] = None
_token_tracker_lock = threading.Lock()


def get_token_tracker(writer: TokenUsageWriter | None = None) -> TokenTracker:
    """获取全局 TokenTracker 单例（线程安全）"""
    global _token_tracker
    if _token_tracker is None:
        with _token_tracker_lock:
            if _token_tracker is None:
                _token_tracker = TokenTracker(writer)
    elif writer is not None:
        _token_tracker._writer = writer
    return _token_tracker
