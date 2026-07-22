"""ElfieNest 数据目录管理 — 所有用户数据存放于 ~/.elfienest/

参考 Hermes Agent 的 ~/.hermes/ 和 OpenClaw 的 ~/.openclaw/ 模式，
项目代码留在 git 仓库，运行时数据全部在用户主目录下。

可通过 ELFIE_HOME 环境变量覆盖默认路径。
"""

import os
import sys
from pathlib import Path


def get_elfie_home() -> Path:
    """获取 ElfieNest 数据主目录（默认 ~/.elfienest/，可通过 ELFIE_HOME 覆盖）

    参考: Hermes get_hermes_home() — HERMES_HOME 环境变量 + ~/.hermes 默认值
    参考: OpenClaw resolveStateDir() — OPENCLAW_STATE_DIR 环境变量 + ~/.openclaw 默认值
    两者都不用 XDG，我们也不用。
    """
    home = Path(os.environ.get("ELFIE_HOME", str(Path.home() / ".elfienest")))
    return home


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
    return get_elfie_home() / "elfies" / elfie_id


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
