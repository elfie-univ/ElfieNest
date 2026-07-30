"""ElfieNest 数据目录管理。

数据根优先级为显式命令参数、``ELFIE_HOME``、运行模式默认值。
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Optional, Union

from ai_runtime.storage.data_layout import (
    FinalRootLayout,
    ensure_final_root_layout,
    final_root_layout,
)

ELFIENEST_RUNTIME_MODE_ENV: Final[str] = "ELFIENEST_RUNTIME_MODE"
ELFIENEST_SOURCE_ROOT_ENV: Final[str] = "ELFIENEST_SOURCE_ROOT"
SOURCE_DATA_HOME_NAME: Final[str] = ".elfienest.local"


@dataclass(frozen=True)
class DataHomeSelectionError(ValueError):
    """数据根参数无法安全解析。"""

    reason: str
    path: Optional[Path] = None

    def __str__(self) -> str:
        if self.path is None:
            return self.reason
        return f"{self.reason}: {self.path}"


def resolve_elfie_home(
    explicit_home: Optional[str] = None,
    *,
    invoking_cwd: Optional[Path] = None,
    runtime_mode: Optional[str] = None,
    source_root: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
    is_frozen: Optional[bool] = None,
) -> Path:
    """解析权威数据根但不创建目录。"""
    environment = os.environ if env is None else env
    cwd = Path.cwd() if invoking_cwd is None else invoking_cwd

    if explicit_home is not None:
        selected = _resolve_user_path(explicit_home, cwd)
        _validate_selected_home(selected)
        return selected

    environment_home = environment.get("ELFIE_HOME")
    if environment_home:
        selected = _resolve_user_path(environment_home, cwd)
        _validate_selected_home(selected)
        return selected

    frozen = bool(getattr(sys, "frozen", False)) if is_frozen is None else is_frozen
    mode = runtime_mode or environment.get(ELFIENEST_RUNTIME_MODE_ENV)
    if frozen or mode == "release" or mode is None:
        return (Path.home() / ".elfienest").resolve(strict=False)
    if mode == "development":
        root = _source_root(source_root, environment)
        return (root / SOURCE_DATA_HOME_NAME).resolve(strict=False)
    raise DataHomeSelectionError(f"不支持的运行模式: {mode!r}")


def select_elfie_home(
    explicit_home: Optional[str] = None,
    *,
    invoking_cwd: Optional[Path] = None,
    runtime_mode: Optional[str] = None,
    source_root: Optional[Path] = None,
) -> Path:
    """解析数据根并发布给当前进程的所有路径助手。"""
    selected = resolve_elfie_home(
        explicit_home,
        invoking_cwd=invoking_cwd,
        runtime_mode=runtime_mode,
        source_root=source_root,
    )
    os.environ["ELFIE_HOME"] = str(selected)
    return selected


def get_elfie_home() -> Path:
    """获取当前进程已经选择的数据主目录。"""
    return resolve_elfie_home()


def _resolve_user_path(value: str, base: Path) -> Path:
    if value == "":
        raise DataHomeSelectionError("数据根不能为空")
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve(strict=False)
    return (base / path).resolve(strict=False)


def _source_root(source_root: Optional[Path], env: Mapping[str, str]) -> Path:
    if source_root is not None:
        return source_root.expanduser().resolve(strict=False)
    environment_root = env.get(ELFIENEST_SOURCE_ROOT_ENV)
    if environment_root:
        return Path(environment_root).expanduser().resolve(strict=False)
    return Path(__file__).resolve().parents[2]


def _validate_selected_home(path: Path) -> None:
    if path.exists() and not path.is_dir():
        raise DataHomeSelectionError("数据根已存在但不是目录", path)


def get_elfie_developer_home() -> Path:
    """获取与生产数据根完全隔离的开发工具数据根。"""
    default = Path.home() / ".elfienest-dev"
    return Path(os.environ.get("ELFIE_DEV_HOME", str(default)))


def get_config_path() -> Path:
    """Return the final runtime policy configuration path."""
    return get_final_root_layout().runtime_config


def get_env_path() -> Path:
    """Return the final owner-only secrets path."""
    return get_final_root_layout().auth_env


def get_food_catalog_path() -> Path:
    """Return the active food package catalog path."""
    return get_final_root_layout().food_packages


def get_food_history_dir() -> Path:
    """Return the food package history directory."""
    return get_final_root_layout().food_packages_history


def get_model_validation_dir() -> Path:
    """Return the model validation report directory."""
    return get_final_root_layout().model_validations


def get_runtime_validation_dir() -> Path:
    """Return the runtime validation report directory."""
    return get_final_root_layout().runtime_validations


def get_model_evidence_path() -> Path:
    """Return the verified model evidence path."""
    return get_final_root_layout().model_evidence


def get_local_files_dir(user_id: str) -> Path:
    """Return one numeric user's isolated local-file directory."""
    return get_final_root_layout().user(user_id).files


def get_db_path() -> Path:
    """系统数据库 (用户、精灵注册、会话)"""
    return get_final_root_layout().nest_database


def data_home_from_db_path(db_path: Union[str, Path]) -> Path:
    """Resolve the selected product root associated with one Nest database."""
    return Path(db_path).expanduser().resolve(strict=False).parent


def get_elfie_config_dir(elfie_id: str) -> Path:
    """每个精灵的独立配置目录"""
    return get_elfie_workspace_dir(elfie_id)


def get_elfie_workspace_dir(elfie_id: str) -> Path:
    """返回经过校验的单精灵工作空间目录。"""
    return get_final_root_layout().elfie(elfie_id).workspace


def get_elfie_conversations_dir(elfie_id: str) -> Path:
    """返回单精灵聊天历史及附件的所属目录。"""
    return get_final_root_layout().elfie(elfie_id).history_database.parent


def get_runtime_dir() -> Path:
    """应用运行时状态目录（PID、健康状态和临时套接字）。"""
    return get_final_root_layout().runtime_state.parent


def get_runtime_state_path() -> Path:
    """Return the final runtime state file path."""
    return get_final_root_layout().runtime_state


def get_runtime_locks_dir() -> Path:
    """Return the final runtime lock directory."""
    return get_final_root_layout().runtime_locks


def get_logs_dir() -> Path:
    """日志目录"""
    return get_final_root_layout().runtime_events_log.parent


def get_runtime_events_log_path() -> Path:
    """Return the append-only runtime event log path."""
    return get_final_root_layout().runtime_events_log


def get_token_usage_log_path() -> Path:
    """Return the append-only token usage log path."""
    return get_final_root_layout().token_usage_log


def get_skills_dir(elfie_id: str) -> Path:
    """Return one final Elfie workspace's evolved-skills directory."""
    return get_final_root_layout().elfie(elfie_id).skills


def get_final_root_layout() -> FinalRootLayout:
    """Resolve all final product paths below the selected data root."""
    return final_root_layout(get_elfie_home())


def ensure_elfie_home() -> None:
    """Create only the shared directories in the final product layout."""
    ensure_final_root_layout(get_elfie_home())
