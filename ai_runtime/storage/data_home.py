"""ElfieNest 数据目录管理。

数据根优先级为显式命令参数、``ELFIE_HOME``、运行模式默认值。
"""

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Optional

_ELFIE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^elfie_[A-Za-z0-9_-]+$")
ELFIENEST_RUNTIME_MODE_ENV: Final[str] = "ELFIENEST_RUNTIME_MODE"
ELFIENEST_SOURCE_ROOT_ENV: Final[str] = "ELFIENEST_SOURCE_ROOT"
SOURCE_DATA_HOME_NAME: Final[str] = ".elfienest.local"


@dataclass(frozen=True)
class InvalidElfieIdError(ValueError):
    """精灵工作区 ID 不可安全映射到目录。"""

    elfie_id: str

    def __str__(self) -> str:
        return f"精灵 ID 不合法，不能用于数据目录: {self.elfie_id!r}"


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
    """主配置文件路径 (YAML 格式)"""
    return get_elfie_home() / "config.yaml"


def get_env_path() -> Path:
    """API Keys 和 secrets (权限 600, gitignored)"""
    return get_elfie_home() / ".env"


def get_food_catalog_path() -> Path:
    """当前生效的粮食配方目录。"""
    return get_elfie_home() / "foods.yaml"


def get_food_history_dir() -> Path:
    """粮食配方历史版本目录。"""
    return get_elfie_home() / "food_history"


def get_validation_dir() -> Path:
    """Runtime 三层本地验证报告目录。"""
    return get_elfie_home() / "validations"


def get_model_evidence_path() -> Path:
    """已验证模型能力证据。"""
    return get_elfie_home() / "model_evidence.yaml"


def get_local_files_dir() -> Path:
    """Agent 可访问的受控本地文件根目录。"""
    return get_elfie_home() / "files"


def get_db_path() -> Path:
    """系统数据库 (用户、精灵注册、会话)"""
    return get_elfie_home() / "nest.db"


def get_elfie_config_dir(elfie_id: str) -> Path:
    """每个精灵的独立配置目录"""
    return get_elfie_workspace_dir(elfie_id)


def get_elfie_workspace_dir(elfie_id: str) -> Path:
    """返回经过校验的单精灵工作空间目录。"""
    if _ELFIE_ID_PATTERN.fullmatch(elfie_id) is None:
        raise InvalidElfieIdError(elfie_id)
    return get_elfie_home() / "elfies" / elfie_id


def get_elfie_conversations_dir(elfie_id: str) -> Path:
    """返回单精灵聊天历史及附件的所属目录。"""
    return get_elfie_workspace_dir(elfie_id) / "conversations"


def get_cache_dir() -> Path:
    """缓存目录"""
    return get_elfie_home() / "cache"


def get_models_dir() -> Path:
    """Ollama 等本地模型的统一存储目录。"""
    return get_elfie_home() / "models"


def get_runtime_dir() -> Path:
    """应用运行时状态目录（PID、健康状态和临时套接字）。"""
    return get_elfie_home() / "runtime"


def get_backups_dir() -> Path:
    """数据库和配置备份目录。"""
    return get_elfie_home() / "backups"


def get_logs_dir() -> Path:
    """日志目录"""
    return get_elfie_home() / "logs"


def get_skills_dir() -> Path:
    """自演化技能库目录"""
    return get_elfie_home() / "skills"


def get_sessions_dir() -> Path:
    """会话历史目录"""
    return get_elfie_home() / "sessions"


def _secure_dir(path: Path) -> None:
    """设置目录为仅所有者可访问（0700），Windows 下无操作

    参考: Hermes _secure_dir() — HERMES_HOME_MODE 环境变量可覆盖权限
    """
    if sys.platform == "win32":
        return
    try:
        mode_str = os.environ.get("ELFIE_HOME_MODE", "").strip()
        mode = int(mode_str, 8) if mode_str else 0o700
    except ValueError:
        mode = 0o700
    try:
        os.chmod(path, mode)
    except (OSError, NotImplementedError):
        pass


def ensure_elfie_home() -> None:
    """确保 ~/.elfienest/ 及所有子目录存在，并设置安全权限

    参考: Hermes ensure_hermes_home() — 创建子目录 + 0700 权限 + 种子默认 SOUL.md
    """
    home = get_elfie_home()
    home.mkdir(parents=True, exist_ok=True)
    _secure_dir(home)

    subdirs = [
        "elfies",
        "cache",
        "models",
        "runtime",
        "backups",
        "logs",
        "skills",
        "sessions",
        "food_history",
        "validations",
        "files",
    ]
    for subdir in subdirs:
        d = home / subdir
        d.mkdir(parents=True, exist_ok=True)
        _secure_dir(d)
