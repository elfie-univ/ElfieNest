from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from elfie.brain.context_types import HomeostasisSnapshot

logger = logging.getLogger("elfie.brain.energy")


class EnergyTimeRegressionError(Exception):
    """Raised when homeostasis receives an older simulation timestamp."""

    def __init__(self, previous_timestamp: float, requested_timestamp: float) -> None:
        self.previous_timestamp = previous_timestamp
        self.requested_timestamp = requested_timestamp
        super().__init__(previous_timestamp, requested_timestamp)

    def __str__(self) -> str:
        return (
            "homeostasis simulation time cannot move backwards: "
            f"{self.previous_timestamp} -> {self.requested_timestamp}"
        )


class HypothalamusEnergy:
    """中层：下丘脑 (生理能量与生物钟作息控制)"""

    def __init__(
        self,
        limits_config: Dict[str, Any] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        # 默认阈值与参数设定 (防配置文件加载失败 fallback)
        config = limits_config.get("limits", {}) if limits_config else {}
        self.energy_config = config.get("energy", {})
        self.fatigue_config = config.get("fatigue", {})

        self.max_energy = self.energy_config.get("max_value", 100.0)
        self.energy = self.energy_config.get("initial_value", 100.0)
        self.depletion_rate = self.energy_config.get("depletion_rate_per_sec", 0.005)

        self.max_fatigue = self.fatigue_config.get("max_value", 100.0)
        self.fatigue = self.fatigue_config.get("initial_value", 0.0)
        self.accumulation_rate = self.fatigue_config.get(
            "accumulation_rate_per_sec", 0.003
        )

        self.hibernation_threshold = self.fatigue_config.get(
            "hibernation_threshold", 95.0
        )
        self.wakeup_threshold = self.fatigue_config.get("wakeup_threshold", 15.0)

        self.is_sleeping = False

        self._clock = clock
        self.last_updated_at = float(clock())
        self.revision = 0

    def update_clock(self, dt: float) -> None:
        """
        生理时钟 Tick 更新
        :param dt: 步长秒数 (由 elfienest 引擎传入)
        """
        self.tick(dt)

    def tick(self, dt: float) -> None:
        """兼容相对时间调用，并统一委托给绝对仿真时钟。"""
        if dt == 0.0:
            previous_sleeping = self.is_sleeping
            self._advance_delta(0.0)
            if self.is_sleeping != previous_sleeping:
                self.revision += 1
            return
        self.advance_to(self.last_updated_at + dt)

    def advance_to(self, timestamp: float) -> None:
        """Advance homeostasis to one absolute simulation timestamp."""
        if timestamp < self.last_updated_at:
            raise EnergyTimeRegressionError(self.last_updated_at, timestamp)
        if timestamp == self.last_updated_at:
            return
        dt = timestamp - self.last_updated_at
        self._advance_delta(dt)
        self.last_updated_at = timestamp
        self.revision += 1

    def _advance_delta(self, dt: float) -> None:
        """Apply the existing homeostasis formulas for a validated delta."""
        if self.is_sleeping:
            # 睡觉状态下恢复体能、消退疲劳 (清空腺苷)
            rec_rate = self.energy_config.get("recovery_rate_sleep_per_sec", 0.05)
            dec_rate = self.fatigue_config.get("decay_rate_sleep_per_sec", 0.04)

            self.energy = min(self.energy + rec_rate * dt, self.max_energy)
            self.fatigue = max(self.fatigue - dec_rate * dt, 0.0)

            # 疲劳消退至足够低，恢复清醒
            if self.fatigue <= self.wakeup_threshold:
                self.is_sleeping = False
                logger.info(
                    f"☀️ [生理钟唤醒] 疲劳已消退至 {self.fatigue:.1f}%，精灵自然醒来！"
                )
        else:
            # 清醒状态下缓慢自然消耗体能、累积疲劳
            remaining_energy = self.energy - self.depletion_rate * dt
            self.energy = 0.0 if remaining_energy <= 1e-12 else remaining_energy
            self.fatigue = min(
                self.fatigue + self.accumulation_rate * dt, self.max_fatigue
            )

            # 疲劳度过高，触发休眠熔断
            if self.fatigue >= self.hibernation_threshold:
                self.is_sleeping = True
                logger.warning(
                    f"💤 [生理钟休眠熔断] 疲劳度达到临界值 {self.fatigue:.1f}%，精灵强制闭眼休眠！"
                )

    def consume_energy_by_action(
        self, is_remote: bool = False, token_count: int = 0, cost_tier: int = 1
    ) -> None:
        """执行大脑思考动作会额外扣减精力

        支持两种调用方式：
        1. 旧方式: consume_energy_by_action(is_remote=True)  — 向后兼容
        2. 新方式: consume_energy_by_action(token_count=1500, cost_tier=3)  — 基于 token 精确计算

        Args:
            is_remote: 是否使用云端模型（旧方式）
            token_count: 本次消耗的 token 数量（新方式）
            cost_tier: 消费层级 (1=低成本本地, 2=中等成本, 3=高成本云端)
        """
        if token_count > 0:
            # 基于 token 精确计算消耗
            base_cost = self.energy_config.get("depletion_per_remote_chat", 2.5)
            cost = base_cost * (token_count / 1000.0) * (cost_tier / 2.0)
        else:
            # 旧方式：固定消耗
            cost = (
                self.energy_config.get("depletion_per_remote_chat", 2.5)
                if is_remote
                else self.energy_config.get("depletion_per_local_chat", 0.5)
            )
        previous_energy = self.energy
        self.energy = max(self.energy - cost, 0.0)
        if self.energy != previous_energy:
            self.revision += 1
        logger.info(
            f"⚡ [动作耗能] 消耗 {cost:.2f} 能量，当前精力剩余: {self.energy:.1f}%"
        )

    def get_energy(self) -> float:
        return self.energy

    def get_fatigue(self) -> float:
        return self.fatigue

    def snapshot(self, at: float) -> HomeostasisSnapshot:
        """Advance first, then seal immutable homeostasis state."""
        self.advance_to(at)
        return HomeostasisSnapshot(
            revision=self.revision,
            captured_at=datetime.fromtimestamp(at, timezone.utc),
            energy=self.energy,
            fatigue=self.fatigue,
            sleeping=self.is_sleeping,
        )
