"""Pure task-target resolution for installed and source lifecycle entrypoints.

This module deliberately knows nothing about databases, ports, processes, UI or
the filesystem contents of a data root.  Callers must collect and revalidate
those facts before constructing :class:`TargetResolutionRequest`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional, Sequence, Tuple


class EntrypointMode(str, Enum):
    """The two supported target-selection namespaces."""

    INSTALLED = "installed"
    SOURCE = "source"


class TargetProvenance(str, Enum):
    """How a resolved task target was selected."""

    INSTALLED_ROOT = "installed_root"
    EXPLICIT = "explicit"
    SESSION = "session"
    DEFAULT = "default"
    CANDIDATE = "candidate"


class DefaultTargetPolicy(str, Enum):
    """Whether the source checkout default is eligible for one command."""

    NEVER = "never"
    ALWAYS = "always"
    RECOGNIZED = "recognized"
    RUNNING = "running"
    USABLE = "usable"
    RECOVERABLE = "recoverable"


@dataclass(frozen=True)
class CommandTargetPolicy:
    """Target-selection contract for one command name."""

    accepts_explicit_home: bool
    default_policy: DefaultTargetPolicy
    requires_target: bool = True


@dataclass(frozen=True)
class TargetCandidate:
    """A previously observed source root, already revalidated by the caller."""

    home: Path
    detail: str = ""


@dataclass(frozen=True)
class TargetResolutionRequest:
    """Facts collected before target selection.

    ``default_eligible`` and ``candidates`` are command-specific facts.  The
    resolver never derives them by reading a port, PID receipt or snapshot.
    """

    mode: EntrypointMode
    command: str
    policy: CommandTargetPolicy
    source_root: Path
    invoking_cwd: Path
    explicit_home: Optional[str] = None
    session_home: Optional[Path] = None
    session_display_home: Optional[str] = None
    session_eligible: bool = True
    default_home: Optional[Path] = None
    default_eligible: bool = False
    candidates: Tuple[TargetCandidate, ...] = ()
    selected_candidate: Optional[Path] = None


@dataclass(frozen=True)
class ResolvedTaskTarget:
    """The one canonical data root a command is allowed to touch."""

    home: Path
    mode: EntrypointMode
    command: str
    provenance: TargetProvenance
    display_home: Optional[str] = None


class TargetResolutionError(ValueError):
    """Base class for typed target-selection failures."""

    code = "target_resolution_failed"


@dataclass(frozen=True)
class ExplicitTargetNotSupported(TargetResolutionError):
    command: str

    code = "explicit_data_home_not_supported"

    def __str__(self) -> str:
        return f"{self.command} 不支持 --data-home"


@dataclass(frozen=True)
class TargetSelectionRequired(TargetResolutionError):
    command: str
    candidates: Tuple[TargetCandidate, ...]

    code = "selection_required"

    def __str__(self) -> str:
        return f"{self.command} 需要选择数据目录；可选任务: " + ", ".join(
            str(candidate.home) for candidate in self.candidates
        )


@dataclass(frozen=True)
class InvalidCandidateSelection(TargetResolutionError):
    command: str
    selected: Path

    code = "invalid_candidate_selection"

    def __str__(self) -> str:
        return f"{self.command} 选择的数据目录未通过重新校验: {self.selected}"


@dataclass(frozen=True)
class TargetNotFound(TargetResolutionError):
    command: str
    detail: str

    code = "target_not_found"

    def __str__(self) -> str:
        return f"{self.command} 没有可操作的数据任务: {self.detail}"


@dataclass(frozen=True)
class InstalledRootMismatch(TargetResolutionError):
    expected: Path
    actual: Path

    code = "installed_root_mismatch"

    def __str__(self) -> str:
        return (
            "安装版 Controller 数据根不一致: "
            f"当前解析={self.expected}，Controller={self.actual}"
        )


def command_target_policy(command: str) -> CommandTargetPolicy:
    """Return the public source command matrix."""

    if command in {"start", "serve"}:
        return CommandTargetPolicy(True, DefaultTargetPolicy.ALWAYS)
    if command in {"restart", "stop"}:
        return CommandTargetPolicy(True, DefaultTargetPolicy.ALWAYS)
    if command in {"status"}:
        return CommandTargetPolicy(False, DefaultTargetPolicy.RECOGNIZED)
    if command in {"web", "mobile", "desktop"}:
        return CommandTargetPolicy(False, DefaultTargetPolicy.RUNNING)
    if command in {
        "config",
        "owner",
        "db",
    }:
        return CommandTargetPolicy(False, DefaultTargetPolicy.USABLE)
    if command in {
        "doctor",
        "uninstall",
    }:
        return CommandTargetPolicy(False, DefaultTargetPolicy.RECOVERABLE)
    return CommandTargetPolicy(False, DefaultTargetPolicy.NEVER, requires_target=False)


def resolve_installed_data_home(
    environment: Mapping[str, str], *, user_home: Path
) -> Path:
    """Resolve the sole installed-product root.

    A non-empty ``ELFIE_HOME`` replaces the default.  It is intentionally
    resolved relative to the stable user-home base, not the caller's cwd.
    """

    configured = environment.get("ELFIE_HOME", "")
    if configured.strip():
        return _canonical_path(configured, user_home)
    return (user_home / ".elfienest").resolve(strict=False)


def resolve_source_default(source_root: Path) -> Path:
    """Resolve the checkout-local source default without ambient env input."""

    return (
        source_root.expanduser().resolve(strict=False) / ".elfienest.local"
    ).resolve(strict=False)


def resolve_source_explicit_home(value: str, *, invoking_cwd: Path) -> Path:
    """Resolve a source ``--data-home`` relative to the invoking cwd."""

    return _canonical_path(value, invoking_cwd)


def resolve_target(request: TargetResolutionRequest) -> ResolvedTaskTarget:
    """Choose exactly one task target using the collected facts."""

    policy = request.policy
    if request.mode is EntrypointMode.INSTALLED:
        if request.explicit_home is not None:
            raise ExplicitTargetNotSupported(request.command)
        if request.default_home is None:
            raise TargetNotFound(request.command, "安装版数据根未解析")
        return ResolvedTaskTarget(
            request.default_home.resolve(strict=False),
            request.mode,
            request.command,
            TargetProvenance.INSTALLED_ROOT,
            None,
        )

    if request.explicit_home is not None:
        if not policy.accepts_explicit_home:
            raise ExplicitTargetNotSupported(request.command)
        return ResolvedTaskTarget(
            resolve_source_explicit_home(
                request.explicit_home, invoking_cwd=request.invoking_cwd
            ),
            request.mode,
            request.command,
            TargetProvenance.EXPLICIT,
            request.explicit_home,
        )

    if request.session_home is not None and request.session_eligible:
        return ResolvedTaskTarget(
            request.session_home.resolve(strict=False),
            request.mode,
            request.command,
            TargetProvenance.SESSION,
            request.session_display_home,
        )

    if request.default_eligible and request.default_home is not None:
        return ResolvedTaskTarget(
            request.default_home.resolve(strict=False),
            request.mode,
            request.command,
            TargetProvenance.DEFAULT,
            _default_display_home(request.mode),
        )

    candidates = _deduplicate_candidates(request.candidates)
    if request.selected_candidate is not None:
        selected = request.selected_candidate.resolve(strict=False)
        if not any(candidate.home == selected for candidate in candidates):
            raise InvalidCandidateSelection(request.command, selected)
        return ResolvedTaskTarget(
            selected,
            request.mode,
            request.command,
            TargetProvenance.CANDIDATE,
            _candidate_display_home(selected, request.invoking_cwd),
        )

    if candidates:
        raise TargetSelectionRequired(request.command, candidates)

    if not policy.requires_target:
        raise TargetNotFound(request.command, "该命令不需要数据任务")
    raise TargetNotFound(request.command, "默认数据目录不符合该命令的运行条件")


def _canonical_path(value: str, base: Path) -> Path:
    if not value.strip():
        raise ValueError("数据目录不能为空")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=False)


def _default_display_home(mode: EntrypointMode) -> Optional[str]:
    if mode is EntrypointMode.SOURCE:
        return ".elfienest.local"
    return None


def _candidate_display_home(selected: Path, invoking_cwd: Path) -> str:
    try:
        return str(selected.resolve(strict=False).relative_to(invoking_cwd.resolve()))
    except ValueError:
        return str(selected)


def _deduplicate_candidates(
    candidates: Sequence[TargetCandidate],
) -> Tuple[TargetCandidate, ...]:
    result: list[TargetCandidate] = []
    seen: set[Path] = set()
    for candidate in candidates:
        home = candidate.home.resolve(strict=False)
        if home in seen:
            continue
        seen.add(home)
        result.append(TargetCandidate(home, candidate.detail))
    return tuple(result)


__all__ = (
    "CommandTargetPolicy",
    "DefaultTargetPolicy",
    "EntrypointMode",
    "ExplicitTargetNotSupported",
    "InstalledRootMismatch",
    "InvalidCandidateSelection",
    "ResolvedTaskTarget",
    "TargetCandidate",
    "TargetNotFound",
    "TargetProvenance",
    "TargetResolutionError",
    "TargetResolutionRequest",
    "TargetSelectionRequired",
    "command_target_policy",
    "resolve_installed_data_home",
    "resolve_source_default",
    "resolve_source_explicit_home",
    "resolve_target",
)
