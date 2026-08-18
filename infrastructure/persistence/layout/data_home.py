"""ElfieNest 数据目录管理。

数据根优先级为显式命令参数、``ELFIE_HOME``、运行模式默认值。
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Optional, Union

from infrastructure.persistence.layout.data_layout import (
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
    mode = runtime_mode or environment.get(ELFIENEST_RUNTIME_MODE_ENV)
    frozen = bool(getattr(sys, "frozen", False)) if is_frozen is None else is_frozen
    installed_base = Path.home() if frozen or mode in {None, "release"} else cwd

    if explicit_home is not None:
        selected = _resolve_user_path(explicit_home, installed_base)
        _validate_selected_home(selected)
        return selected

    environment_home = environment.get("ELFIE_HOME")
    if environment_home:
        selected = _resolve_user_path(environment_home, installed_base)
        _validate_selected_home(selected)
        return selected

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


def get_configs_dir() -> Path:
    """返回生产配置目录。"""
    return get_elfie_home() / "configs"


def get_credentials_dir() -> Path:
    """返回生产凭据目录。"""
    return get_configs_dir() / "credentials"


def get_oauth_credentials_dir() -> Path:
    """返回结构化 OAuth 凭据目录。"""
    return get_credentials_dir() / "oauth"


def get_reports_dir() -> Path:
    """返回可重新生成的运行报告目录。"""
    return get_elfie_home() / "reports"


def get_report_database_path(data_home: Optional[Path] = None) -> Path:
    """Return the append-only model/Food/tool report database for one data root."""
    root = data_home or get_elfie_home()
    return root / "reports" / "ai-runtime.sqlite"


def get_report_exports_dir() -> Path:
    """返回按需生成、永不读回的人工报告导出目录。"""
    return get_reports_dir() / "exports"


def get_config_path() -> Path:
    """Runtime 主配置文件路径。"""
    return get_final_root_layout().runtime_config


def get_provider_config_path() -> Path:
    """Provider 实例配置文件路径。"""
    return get_configs_dir() / "providers.yaml"


def get_provider_catalog_path() -> Path:
    """可远程更新的 Provider 元数据覆盖包路径。"""
    return get_configs_dir() / "provider-catalog.yaml"


def get_tool_config_path() -> Path:
    """工具配置文件路径。"""
    return get_configs_dir() / "tools.yaml"


def get_model_execution_config_paths() -> tuple[Path, Path, Path]:
    """返回影响模型执行热加载的全部正式配置文件。"""
    return (
        get_config_path(),
        get_provider_config_path(),
        get_tool_config_path(),
    )


def get_env_path() -> Path:
    """API Keys 和 secrets (权限 600, gitignored)"""
    return get_final_root_layout().auth_env


def get_model_validation_dir() -> Path:
    """Return the model validation report directory."""
    return get_final_root_layout().model_validations


def get_runtime_validation_dir() -> Path:
    """Return the runtime validation report directory."""
    return get_final_root_layout().runtime_validations


def get_local_files_dir(user_id: str) -> Path:
    """Return one numeric user's isolated local-file directory."""
    return get_final_root_layout().user(user_id).files


def get_db_path() -> Path:
    """系统数据库 (用户、精灵注册、会话)"""
    return get_final_root_layout().nest_database


def data_home_from_db_path(db_path: Union[str, Path]) -> Path:
    """Resolve the selected product root associated with one Nest database."""
    if str(db_path) == ":memory:":
        raise DataHomeSelectionError("SQLite 内存数据库不能作为产品数据根")
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
    """返回日志目录。"""
    return get_elfie_home() / "logs"


def get_skills_dir(elfie_id: str) -> Path:
    """Return one final Elfie workspace's evolved-skills directory."""
    return get_final_root_layout().elfie(elfie_id).skills


def get_final_root_layout() -> FinalRootLayout:
    """Resolve all final product paths below the selected data root."""
    return final_root_layout(get_elfie_home())


def ensure_elfie_home() -> None:
    """确保数据根及所有子目录存在，并设置安全权限。"""
    ensure_final_root_layout(get_elfie_home())
