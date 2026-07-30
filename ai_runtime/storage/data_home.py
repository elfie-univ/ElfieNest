"""ElfieNest 数据目录管理 — 所有用户数据存放于 ~/.elfienest/

参考 Hermes Agent 的 ~/.hermes/ 和 OpenClaw 的 ~/.openclaw/ 模式，
项目代码留在 git 仓库，运行时数据全部在用户主目录下。

可通过 ELFIE_HOME 环境变量覆盖默认路径。
"""

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_ELFIE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^elfie_[A-Za-z0-9_-]+$")
_FINAL_ELFIE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]{8}$")
_NUMERIC_USER_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]+$")
_AVATAR_EXTENSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(?:png|jpe?g|webp)$")


@dataclass(frozen=True)
class InvalidElfieIdError(ValueError):
    """精灵工作区 ID 不可安全映射到目录。"""

    elfie_id: str

    def __str__(self) -> str:
        return f"精灵 ID 不合法，不能用于数据目录: {self.elfie_id!r}"


@dataclass(frozen=True)
class InvalidUserIdError(ValueError):
    """用户资产 ID 不可安全映射到目录。"""

    user_id: str

    def __str__(self) -> str:
        return f"用户 ID 不合法，不能用于数据目录: {self.user_id!r}"


@dataclass(frozen=True)
class InvalidAvatarExtensionError(ValueError):
    """用户头像扩展名不可安全映射到文件名。"""

    extension: str

    def __str__(self) -> str:
        return f"头像扩展名不合法，不能用于数据目录: {self.extension!r}"


@dataclass(frozen=True)
class DataRootConflictError(ValueError):
    """生产数据根与开发工具数据根解析后发生重叠。"""

    production_home: Path
    developer_home: Path

    def __str__(self) -> str:
        return (
            "生产数据根和开发工具数据根不能重叠: "
            f"production={self.production_home}, developer={self.developer_home}"
        )


def _paths_overlap(first: Path, second: Path) -> bool:
    left, right = (path.expanduser().resolve(strict=False) for path in (first, second))
    return left == right or left in right.parents or right in left.parents


def assert_distinct_data_roots(production_home: Path, developer_home: Path) -> None:
    """拒绝生产数据根与开发工具数据根解析后双向重叠。"""
    if _paths_overlap(production_home, developer_home):
        raise DataRootConflictError(production_home, developer_home)


def ensure_distinct_data_roots() -> None:
    """校验当前环境下生产和开发工具数据根互不重叠。"""
    assert_distinct_data_roots(get_elfie_home(), get_elfie_developer_home())


def get_elfie_home() -> Path:
    """获取 ElfieNest 数据主目录（默认 ~/.elfienest/，可通过 ELFIE_HOME 覆盖）

    参考: Hermes get_hermes_home() — HERMES_HOME 环境变量 + ~/.hermes 默认值
    参考: OpenClaw resolveStateDir() — OPENCLAW_STATE_DIR 环境变量 + ~/.openclaw 默认值
    两者都不用 XDG，我们也不用。
    """
    home = Path(os.environ.get("ELFIE_HOME", str(Path.home() / ".elfienest")))
    return home


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


def get_final_providers_config_path() -> Path:
    """最终模型供应商配置路径。"""
    return get_elfie_home() / "configs" / "providers.yaml"


def get_final_auth_env_path() -> Path:
    """最终本地密钥环境文件路径。"""
    return get_elfie_home() / "configs" / "auth.env"


def get_final_runtime_config_path() -> Path:
    """最终 Runtime 配置路径。"""
    return get_elfie_home() / "configs" / "runtime.yaml"


def get_final_food_packages_path() -> Path:
    """最终粮食包配置路径。"""
    return get_elfie_home() / "configs" / "food-packages.yaml"


def get_final_food_packages_history_dir() -> Path:
    """最终粮食包历史版本目录。"""
    return get_elfie_home() / "configs" / "food-packages-history"


def get_final_model_evidence_path() -> Path:
    """最终模型能力证据路径。"""
    return get_elfie_home() / "reports" / "model-evidence.yaml"


def get_final_model_validations_dir() -> Path:
    """最终模型验证报告目录。"""
    return get_elfie_home() / "reports" / "model-validations"


def get_final_runtime_validations_dir() -> Path:
    """最终 Runtime 验证报告目录。"""
    return get_elfie_home() / "reports" / "runtime-validations"


def get_final_runtime_state_path() -> Path:
    """最终 Runtime 状态文件路径。"""
    return get_elfie_home() / "runtime" / "runtime.json"


def get_final_runtime_locks_dir() -> Path:
    """最终 Runtime 锁目录。"""
    return get_elfie_home() / "runtime" / "locks"


def get_final_logs_dir() -> Path:
    """最终日志目录。"""
    return get_elfie_home() / "logs"


def _parse_numeric_user_id(user_id: str) -> str:
    if _NUMERIC_USER_ID_PATTERN.fullmatch(user_id) is None:
        raise InvalidUserIdError(user_id)
    return user_id


def _parse_avatar_extension(extension: str) -> str:
    extension = extension.lower()
    if _AVATAR_EXTENSION_PATTERN.fullmatch(extension) is None:
        raise InvalidAvatarExtensionError(extension)
    return extension


def get_final_user_assets_dir(user_id: str) -> Path:
    """最终用户资产根目录。"""
    return get_elfie_home() / "assets" / "users" / _parse_numeric_user_id(user_id)


def get_final_user_avatar_path(user_id: str, extension: str) -> Path:
    """最终用户头像文件路径。"""
    return get_final_user_assets_dir(user_id) / (
        f"avatar.{_parse_avatar_extension(extension)}"
    )


def get_final_user_files_dir(user_id: str) -> Path:
    """最终用户可管理文件目录。"""
    return get_final_user_assets_dir(user_id) / "files"


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


def _parse_final_elfie_id(elfie_id: str) -> str:
    if _FINAL_ELFIE_ID_PATTERN.fullmatch(elfie_id) is None:
        raise InvalidElfieIdError(elfie_id)
    return elfie_id


def get_final_elfie_workspace_dir(elfie_id: str) -> Path:
    """最终单精灵工作空间目录。"""
    return get_elfie_home() / "elfies" / _parse_final_elfie_id(elfie_id)


def get_final_elfie_assets_dir(elfie_id: str) -> Path:
    """最终单精灵资产目录。"""
    return get_final_elfie_workspace_dir(elfie_id) / "assets"


def get_final_elfie_godot_dir(elfie_id: str) -> Path:
    """最终单精灵 Godot 导出目录。"""
    return get_final_elfie_workspace_dir(elfie_id) / "godot"


def get_final_elfie_profile_path(elfie_id: str) -> Path:
    """最终单精灵档案文件路径。"""
    return get_final_elfie_workspace_dir(elfie_id) / "profile" / "profile.yaml"


def get_final_elfie_skills_dir(elfie_id: str) -> Path:
    """最终单精灵技能目录。"""
    return get_final_elfie_workspace_dir(elfie_id) / "skills"


def get_final_elfie_history_path(elfie_id: str) -> Path:
    """最终单精灵聊天历史数据库路径。"""
    return get_final_elfie_workspace_dir(elfie_id) / "conversations" / "history.sqlite"


def get_final_elfie_attachments_dir(elfie_id: str) -> Path:
    """最终单精灵聊天附件目录。"""
    return get_final_elfie_workspace_dir(elfie_id) / "conversations" / "attachments"


def get_final_elfie_knowledge_path(elfie_id: str) -> Path:
    """最终单精灵知识数据库路径。"""
    return get_final_elfie_workspace_dir(elfie_id) / "memory" / "knowledge.sqlite"


def get_final_elfie_daily_memory_dir(elfie_id: str) -> Path:
    """最终单精灵每日记忆目录。"""
    return get_final_elfie_workspace_dir(elfie_id) / "memory" / "daily"


def get_final_elfie_people_memory_dir(elfie_id: str) -> Path:
    """最终单精灵人物记忆目录。"""
    return get_final_elfie_workspace_dir(elfie_id) / "memory" / "people"


def get_final_elfie_concepts_memory_dir(elfie_id: str) -> Path:
    """最终单精灵概念记忆目录。"""
    return get_final_elfie_workspace_dir(elfie_id) / "memory" / "concepts"


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
