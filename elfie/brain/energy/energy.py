from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Literal

from elfie.brain.energy.contracts import (
    CognitiveBudgetReservation,
    EnergySnapshot,
)
from elfie.brain.state_lifecycle import StateRestoreError
from elfie.message_types import TurnId

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


@dataclass(frozen=True)
class EnergyCheckpoint:
    """Persistence-neutral checkpoint for homeostasis and its clock."""

    revision: int
    last_updated_at: float
    energy: float
    fatigue: float
    sleeping: bool
    emergency_reserve: float


class CognitiveBudgetUnavailableError(RuntimeError):
    """Raised when neither normal energy nor emergency reserve can admit a Turn."""


class EnergySystem:
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

        cognitive = config.get("cognitive", {})
        self.long_reasoning_min_energy = float(
            cognitive.get("long_reasoning_min_energy", 70.0)
        )
        self.degraded_energy_threshold = float(
            cognitive.get("degraded_energy_threshold", 30.0)
        )
        self.emergency_energy_threshold = float(
            cognitive.get("emergency_energy_threshold", 10.0)
        )
        self.long_reasoning_max_fatigue = float(
            cognitive.get("long_reasoning_max_fatigue", 50.0)
        )
        self.degraded_fatigue_threshold = float(
            cognitive.get("degraded_fatigue_threshold", 75.0)
        )
        self.emergency_fatigue_threshold = float(
            cognitive.get("emergency_fatigue_threshold", 90.0)
        )
        self.emergency_reserve_capacity = float(
            cognitive.get("emergency_reserve_capacity", 10.0)
        )
        self.emergency_reserve_recovery_rate = float(
            cognitive.get("emergency_reserve_recovery_rate_sleep_per_sec", 0.01)
        )
        self.emergency_reserve = self.emergency_reserve_capacity
        self._cognitive_reservations: dict[TurnId, CognitiveBudgetReservation] = {}

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
            self.emergency_reserve = min(
                self.emergency_reserve_capacity,
                self.emergency_reserve + self.emergency_reserve_recovery_rate * dt,
            )

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

    def snapshot(self, at: float) -> EnergySnapshot:
        """Advance first, then seal immutable homeostasis state."""
        self.advance_to(at)
        mode, long_allowed, budget = self.cognitive_policy()
        return EnergySnapshot(
            revision=self.revision,
            captured_at=datetime.fromtimestamp(at, timezone.utc),
            energy=self.energy,
            fatigue=self.fatigue,
            sleeping=self.is_sleeping,
            cognitive_mode=mode,
            long_reasoning_allowed=long_allowed,
            available_cognitive_budget=budget,
            normal_budget_available=self.activity_budget_available(),
            emergency_reserve_available=self._emergency_reserve_available(),
            reserved_cognitive_budget=self.reserved_cognitive_budget(),
        )

    def reserve_cognitive_budget(
        self,
        turn_id: TurnId,
        *,
        responsive: bool = False,
    ) -> CognitiveBudgetReservation:
        """Reserve a bounded allowance before one ReasoningRun is admitted."""
        existing = self._cognitive_reservations.get(turn_id)
        if existing is not None:
            return existing
        mode = self.cognitive_policy()[0]
        requested = {
            "emergency": 1.0,
            "degraded": 2.0,
            "normal": 5.0,
            "long": 8.0,
        }[mode]
        if mode == "emergency":
            available = self._emergency_reserve_available()
            source: Literal[
                "normal", "emergency_reserve", "responsive"
            ] = "emergency_reserve"
            if responsive and available <= 0.0:
                # Energy controls reasoning depth, but an owner interaction
                # must retain one bounded fast reply even after a previous
                # failure consumed the persistent reserve.
                available = 1.0
                source = "responsive"
        else:
            available = self.activity_budget_available()
            source = "normal"
        granted = min(requested, available)
        if granted <= 0.0:
            raise CognitiveBudgetUnavailableError(
                f"no {source} budget is available for {turn_id}"
            )
        self.revision += 1
        reservation = CognitiveBudgetReservation(
            turn_id=turn_id,
            mode=mode,
            source=source,
            granted=granted,
            owner_revision=self.revision,
        )
        self._cognitive_reservations[turn_id] = reservation
        return reservation

    def settle_cognitive_budget(
        self,
        turn_id: TurnId,
        *,
        consumed: float,
    ) -> float:
        """Charge actual bounded work once and release the unused reservation."""
        reservation = self._cognitive_reservations.pop(turn_id, None)
        if reservation is None:
            return 0.0
        charged = min(reservation.granted, max(0.0, float(consumed)))
        if reservation.source == "emergency_reserve":
            self.emergency_reserve = max(0.0, self.emergency_reserve - charged)
        elif reservation.source == "normal":
            self.energy = max(0.0, self.energy - charged)
        self.revision += 1
        return charged

    def release_cognitive_budget(self, turn_id: TurnId) -> bool:
        """Release a reservation when no cognitive work started."""
        if self._cognitive_reservations.pop(turn_id, None) is None:
            return False
        self.revision += 1
        return True

    def activity_budget_available(self) -> float:
        """Return normal allowance only; Activity can never spend the reserve."""
        reserved = sum(
            item.granted
            for item in self._cognitive_reservations.values()
            if item.source == "normal"
        )
        return max(0.0, self.energy - self.emergency_energy_threshold - reserved)

    def reserved_cognitive_budget(self) -> float:
        return sum(item.granted for item in self._cognitive_reservations.values())

    def _emergency_reserve_available(self) -> float:
        reserved = sum(
            item.granted
            for item in self._cognitive_reservations.values()
            if item.source == "emergency_reserve"
        )
        return max(0.0, self.emergency_reserve - reserved)

    def cognitive_policy(
        self,
    ) -> tuple[Literal["normal", "long", "degraded", "emergency"], bool, float]:
        """Return deterministic cognitive admission derived from homeostasis.

        The policy only limits reasoning depth and budget. It does not select a
        semantic goal or produce an external action.
        """
        budget = max(0.0, min(100.0, (self.energy / self.max_energy) * 100.0))
        if (
            self.is_sleeping
            or self.energy <= self.emergency_energy_threshold
            or self.fatigue >= self.emergency_fatigue_threshold
        ):
            return "emergency", False, budget
        if (
            self.energy <= self.degraded_energy_threshold
            or self.fatigue >= self.degraded_fatigue_threshold
        ):
            return "degraded", False, budget
        if (
            self.energy >= self.long_reasoning_min_energy
            and self.fatigue <= self.long_reasoning_max_fatigue
        ):
            return "long", True, budget
        return "normal", False, budget

    def can_start_long_reasoning(self) -> bool:
        """Whether the current state permits a bounded long cognitive run."""
        return self.cognitive_policy()[1]

    def checkpoint(self) -> EnergyCheckpoint:
        """Seal mutable energy, fatigue, sleep and simulation-clock state."""
        return EnergyCheckpoint(
            revision=self.revision,
            last_updated_at=self.last_updated_at,
            energy=self.energy,
            fatigue=self.fatigue,
            sleeping=self.is_sleeping,
            emergency_reserve=self.emergency_reserve,
        )

    def validate_checkpoint(self, checkpoint: EnergyCheckpoint) -> None:
        """Reject an older or physically impossible homeostasis checkpoint."""
        if checkpoint.revision < self.revision:
            raise StateRestoreError(
                "energy checkpoint revision is older than current state"
            )
        if (
            checkpoint.revision == self.revision
            and checkpoint.last_updated_at < self.last_updated_at
        ):
            raise StateRestoreError(
                "energy checkpoint simulation time is older than current state"
            )
        if not 0.0 <= checkpoint.energy <= self.max_energy:
            raise ValueError("energy checkpoint value out of range")
        if not 0.0 <= checkpoint.fatigue <= self.max_fatigue:
            raise ValueError("fatigue checkpoint value out of range")
        if not 0.0 <= checkpoint.emergency_reserve <= self.emergency_reserve_capacity:
            raise ValueError("energy emergency reserve out of range")

    def restore(self, checkpoint: EnergyCheckpoint) -> None:
        """Restore a committed homeostasis checkpoint without rewinding it."""
        self.validate_checkpoint(checkpoint)
        self.last_updated_at = checkpoint.last_updated_at
        self.revision = checkpoint.revision
        self.energy = checkpoint.energy
        self.fatigue = checkpoint.fatigue
        self.is_sleeping = checkpoint.sleeping
        self.emergency_reserve = checkpoint.emergency_reserve
        self._cognitive_reservations.clear()
