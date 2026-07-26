"""Plan release work across native build runners without inventing artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Sequence

from scripts.package_python_core import TARGETS

SUPPORTED_TARGETS: Final[tuple[str, ...]] = TARGETS


class ReleasePlanError(RuntimeError):
    """Raised when a requested release matrix is not well-defined."""


@dataclass(frozen=True)
class ReleasePlan:
    """The local and remote work needed for one requested release matrix."""

    native_targets: tuple[str, ...]
    requires_native_runner: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        """Whether the current runner can execute every requested target."""
        return not self.requires_native_runner


def plan_release(requested_targets: Sequence[str], host_target: str) -> ReleasePlan:
    """Partition a complete, unique target request by the active native runner."""
    targets = tuple(requested_targets)
    if not targets:
        raise ReleasePlanError("release-targets-empty")
    unknown = tuple(target for target in targets if target not in SUPPORTED_TARGETS)
    if unknown:
        raise ReleasePlanError(f"release-target-unsupported targets={','.join(unknown)}")
    if len(set(targets)) != len(targets):
        raise ReleasePlanError("release-targets-duplicated")
    if host_target not in SUPPORTED_TARGETS:
        raise ReleasePlanError(f"release-host-target-unsupported target={host_target}")
    native_targets = tuple(target for target in targets if target == host_target)
    remote_targets = tuple(target for target in targets if target != host_target)
    return ReleasePlan(
        native_targets=native_targets,
        requires_native_runner=remote_targets,
    )
