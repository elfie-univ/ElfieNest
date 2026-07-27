"""终端首启向导：复用 Web 的五步 Setup 状态与 feature service。"""

from __future__ import annotations

from ai_runtime.storage.data_home import get_config_path, get_db_path
from app.features.configuration.runtime_store import (
    read_runtime_config,
    write_runtime_config,
)
from app.features.setup.ollama import OllamaSetupService
from app.features.setup.progress import complete_setup_step, get_setup_progress
from app.features.setup.service import (
    SetupAlreadyCompleteError,
    create_first_owner_account,
    needs_setup,
)
from app.infrastructure.ollama_platform import OllamaPlatformAdapter
from app.infrastructure.persistence.nest_repository import SQLiteNestRepository
from app.infrastructure.persistence.store import get_db, init_db, migrate_db_if_needed
from app.interfaces.cli.tui.common import (
    clear_screen,
    input_password,
    input_text,
    print_banner,
    print_success_panel,
    print_tui_panel,
    rich_console,
)


def run_setup_wizard() -> None:
    """Complete exactly the same persisted five Setup steps as the Web wizard."""
    clear_screen()
    print_banner()
    print_tui_panel("ElfieNest Setup Wizard", "首次启动前完成五步初始化")
    db_path = str(get_db_path())
    init_db(db_path)
    migrate_db_if_needed(db_path)
    if not needs_setup(db_path):
        print("  ⚠️  系统已初始化，跳过设置向导")
        return
    if not _complete_owner(db_path):
        return
    if not _complete_ollama(db_path):
        return
    if not _complete_nest(db_path):
        return
    if not _complete_model(db_path):
        return
    _complete_confirmation(db_path)


def _complete_owner(db_path: str) -> bool:
    progress = get_setup_progress(db_path)
    if progress.current_step != 1:
        return True
    _print_step("1/5", "创建 Owner 账号")
    username = input_text("  Owner 登录名", "owner") or "owner"
    display_name = input_text("  Owner 显示名称", username) or username
    password = input_password("  Owner 密码")
    if password is None:
        print("  ❌ 当前终端无法安全输入 Owner 密码，设置已取消")
        return False
    if not 3 <= len(username.strip()) <= 32 or not 6 <= len(password) <= 128:
        print("  ❌ Owner 凭据不符合要求，设置已取消")
        return False
    try:
        create_first_owner_account(
            db_path,
            username=username.strip(),
            password=password,
            display_name=display_name.strip(),
        )
    except SetupAlreadyCompleteError as error:
        print(f"  ⚠️  Owner 已存在或创建失败: {error}")
        return False
    print(f"  ✅ Owner '{username.strip()}' 创建成功")
    return True


def _complete_ollama(db_path: str) -> bool:
    progress = get_setup_progress(db_path)
    if progress.current_step != 2:
        return True
    _print_step("2/5", "设备与离线保障")
    print("  Ollama 是断网或云端不可用时的本地备份，可维持精灵基本能力。")
    print("  可选项：绑定已有公共 Ollama、从官网安装，或暂时跳过。")
    choice = (
        (input_text("  选择 [skip/bind/install]", "skip") or "skip").strip().lower()
    )
    if choice == "skip":
        complete_setup_step(db_path, step=2, decision="skipped")
        return True
    if choice == "bind":
        endpoint = input_text("  已有 Ollama endpoint", "http://127.0.0.1:11434")
        if not endpoint:
            print("  ❌ 需要固定 endpoint")
            return False
        try:
            _ollama_service().bind_existing(db_path=db_path, endpoint=endpoint.strip())
        except (RuntimeError, ValueError) as error:
            print(f"  ❌ 无法绑定 Ollama: {error}")
            return False
        return True
    if choice == "install":
        confirmed = (
            input_text("  确认从 Ollama 官方站下载并运行安装程序？[y/N]", "n") or "n"
        ).lower()
        if confirmed != "y":
            print("  已取消 Ollama 安装")
            return False
        try:
            _ollama_service().install_official(
                db_path=db_path,
                endpoint="http://127.0.0.1:11434",
                user_confirmed=True,
            )
        except (RuntimeError, ValueError, PermissionError) as error:
            print(f"  ❌ 官方 Ollama 安装失败: {error}")
            return False
        return True
    print("  ❌ 无效选择；未修改 Setup 状态")
    return False


def _complete_nest(db_path: str) -> bool:
    progress = get_setup_progress(db_path)
    if progress.current_step != 3:
        return True
    _print_step("3/5", "精灵巢设置")
    raw = input_text("  床位数（4-32）", "4") or "4"
    try:
        bed_count = int(raw)
    except ValueError:
        print("  ❌ 床位数必须为整数")
        return False
    if not 4 <= bed_count <= 32:
        print("  ❌ 床位数必须在 4 到 32 之间")
        return False
    with get_db(db_path) as conn:
        SQLiteNestRepository(conn).set_desired_bed_count(bed_count)
        conn.commit()
    complete_setup_step(db_path, step=3)
    return True


def _complete_model(db_path: str) -> bool:
    progress = get_setup_progress(db_path)
    if progress.current_step != 4:
        return True
    _print_step("4/5", "模型与粮食")
    choice = (
        (input_text("  选择 [skip/existing/pull]", "skip") or "skip").strip().lower()
    )
    if choice == "skip":
        complete_setup_step(db_path, step=4, decision="skipped")
        return True
    model_reference = input_text("  模型（provider_id/model_id）", "")
    if not model_reference:
        print("  ❌ 需要完整 provider_id/model_id")
        return False
    try:
        service = _ollama_service()
        if choice == "existing":
            service.configure_installed_model(
                db_path=db_path,
                model_reference=model_reference.strip(),
            )
            return True
        if choice == "pull":
            confirmed = (input_text("  确认下载该模型？[y/N]", "n") or "n").lower()
            if confirmed != "y":
                print("  已取消模型下载")
                return False
            service.pull_and_configure_model(
                db_path=db_path,
                model_reference=model_reference.strip(),
            )
            return True
    except (RuntimeError, ValueError) as error:
        print(f"  ❌ 模型配置失败: {error}")
        return False
    print("  ❌ 无效选择；未修改 Setup 状态")
    return False


def _complete_confirmation(db_path: str) -> None:
    progress = get_setup_progress(db_path)
    if progress.current_step != 5 or progress.complete:
        return
    _print_step("5/5", "确认完成")
    confirmed = (input_text("  完成初始化并进入管理菜单？[y/N]", "y") or "y").lower()
    if confirmed != "y":
        print("  已保留当前进度；可稍后继续。")
        return
    complete_setup_step(db_path, step=5)
    print_success_panel(["设置完成！", "启动服务: elfienest"])


def _ollama_service() -> OllamaSetupService:
    """Compose the same fixed-binding service used by the Setup API."""
    config_path = get_config_path()
    return OllamaSetupService(
        adapter=OllamaPlatformAdapter(),
        read_config=lambda: read_runtime_config(config_path),
        write_config=lambda config: write_runtime_config(config_path, config),
    )


def _print_step(step: str, title: str) -> None:
    console = rich_console()
    if console is None:
        print(f"  【步骤 {step}】{title}")
        return
    console.print(f"  [bold magenta]步骤 {step}[/] [white]{title}[/]")
