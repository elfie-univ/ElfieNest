#!/bin/bash
# ElfieNest 安装脚本
# 安装 elfie 命令到系统

set -e

echo ""
echo "🦊 ElfieNest 安装脚本"
echo "======================"
echo ""

# 获取项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
INSTALL_LOG_PATH="${TMPDIR:-/tmp}/elfienest-install.log"

path_contains_dir() {
    local dir="$1"
    [[ ":$PATH:" == *":$dir:"* ]]
}

ensure_writable_dir() {
    local dir="$1"
    mkdir -p "$dir" 2>/dev/null || return 1
    [ -w "$dir" ]
}

python_is_39() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 9) else 1)' >/dev/null 2>&1
}

python_has_web_dependencies() {
    python_is_39 "$1" || return 1
    "$1" -c 'import fastapi, uvicorn, multipart, rich, pydantic, websockets' >/dev/null 2>&1
}

find_python39() {
    local candidate resolved

    for candidate in "${ELFIE_PYTHON:-}" python3.9 python3; do
        [ -n "$candidate" ] || continue
        resolved="$(command -v "$candidate" 2>/dev/null || true)"
        [ -n "$resolved" ] || resolved="$candidate"
        if [ -x "$resolved" ] && python_is_39 "$resolved"; then
            echo "$resolved"
            return
        fi
    done

    echo ""
}

ensure_project_venv() {
    local system_python
    local venv_python

    system_python="$(find_python39)"
    if [ -z "$system_python" ]; then
        echo "❌ 未找到 Python 3.9。请安装 Python 3.9，或设置 ELFIE_PYTHON 指向 Python 3.9 可执行文件"
        exit 1
    fi

    venv_python="$PROJECT_ROOT/.venv/bin/python3"
    if [ -x "$venv_python" ] && ! python_is_39 "$venv_python"; then
        echo "⚠️  检测到项目 .venv 不是 Python 3.9，正在用 Python 3.9 重建"
        "$system_python" -m venv --clear "$PROJECT_ROOT/.venv"
    elif [ ! -x "$venv_python" ]; then
        echo "🐍 正在创建项目运行环境: $PROJECT_ROOT/.venv"
        "$system_python" -m venv "$PROJECT_ROOT/.venv"
    fi

    "$venv_python" -m ensurepip --upgrade >/dev/null 2>&1 || true

    if python_has_web_dependencies "$venv_python"; then
        echo "✅ 项目依赖已就绪"
        return
    fi

    echo "📦 正在安装/更新项目依赖..."
    echo "   详情日志: $INSTALL_LOG_PATH"
    if ! "$venv_python" -m pip install --disable-pip-version-check -r "$PROJECT_ROOT/requirements.txt" > "$INSTALL_LOG_PATH" 2>&1; then
        echo "❌ 项目依赖安装失败，最近日志:"
        tail -40 "$INSTALL_LOG_PATH" || true
        exit 1
    fi

    if ! python_has_web_dependencies "$venv_python"; then
        echo "❌ 项目依赖安装后仍不可用，请检查 pip 输出"
        exit 1
    fi

    echo "✅ 项目依赖已就绪"
}

choose_install_dir() {
    local dir

    if [ "$EUID" -eq 0 ]; then
        echo "/usr/local/bin"
        return
    fi

    for dir in "$HOME/.local/bin" "$HOME/bin" "/usr/local/bin"; do
        if path_contains_dir "$dir" && ensure_writable_dir "$dir"; then
            echo "$dir"
            return
        fi
    done

    IFS=":" read -ra path_dirs <<< "$PATH"
    for dir in "${path_dirs[@]}"; do
        if [[ "$dir" == "$HOME"/* ]] && ensure_writable_dir "$dir"; then
            echo "$dir"
            return
        fi
    done

    echo "$HOME/.local/bin"
}

path_line_for_dir() {
    local dir="$1"
    if [ "$dir" = "$HOME/.local/bin" ]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"'
    elif [ "$dir" = "$HOME/bin" ]; then
        echo 'export PATH="$HOME/bin:$PATH"'
    else
        echo "export PATH=\"$dir:\$PATH\""
    fi
}

configure_user_path() {
    local install_dir="$1"
    local shell_name
    local profile_file
    local path_line

    if path_contains_dir "$install_dir"; then
        echo "✅ $install_dir 已在当前 PATH 中，本终端可直接使用 elfie"
        return
    fi

    shell_name="$(basename "${SHELL:-}")"
    if [ "$shell_name" = "bash" ]; then
        profile_file="$HOME/.bashrc"
    else
        profile_file="$HOME/.zshrc"
    fi

    path_line="$(path_line_for_dir "$install_dir")"

    touch "$profile_file"
    if grep -Fq "$path_line" "$profile_file"; then
        echo "✅ $profile_file 已包含 PATH 配置"
    else
        {
            echo ""
            echo "# ElfieNest CLI"
            echo "$path_line"
        } >> "$profile_file"
        echo "✅ 已写入 PATH 配置: $profile_file"
    fi

    echo ""
    echo "✅ 新打开的终端可直接使用 elfie"
    echo "ℹ️  当前终端如果还找不到 elfie，可直接运行: $install_dir/elfie"
}

remove_old_wrapper_if_same_project() {
    local old_path="$1"
    if [ "$old_path" = "$INSTALL_DIR/elfie" ] || [ ! -f "$old_path" ]; then
        return
    fi
    if grep -Fq "cd \"$PROJECT_ROOT\"" "$old_path" 2>/dev/null; then
        rm -f "$old_path"
        echo "🧹 已清理旧安装: $old_path"
    fi
}

# 检测安装位置
if [ "$EUID" -eq 0 ]; then
    echo "📦 安装模式: 系统安装"
else
    echo "📦 安装模式: 用户安装"
fi

INSTALL_DIR="$(choose_install_dir)"
echo "📍 安装位置: $INSTALL_DIR"
echo ""

# 创建目录
mkdir -p "$INSTALL_DIR"

ensure_project_venv

if [ -x "$INSTALL_DIR/elfie" ]; then
    INSTALL_ACTION="更新"
else
    INSTALL_ACTION="安装"
fi

# 创建 elfie 命令（指向 elfie.sh）
cat > "$INSTALL_DIR/elfie" << INNER_EOF
#!/bin/bash
cd "$PROJECT_ROOT"
./elfie.sh "\$@"
INNER_EOF

chmod +x "$INSTALL_DIR/elfie"

remove_old_wrapper_if_same_project "$HOME/bin/elfie"
remove_old_wrapper_if_same_project "$HOME/.local/bin/elfie"

echo "✅ 已${INSTALL_ACTION} elfie 命令"
echo ""

# 检查 PATH
if [ "$EUID" -ne 0 ]; then
    configure_user_path "$INSTALL_DIR"
fi

echo "🎉 安装完成！"
echo ""
echo "使用方法:"
echo "  elfie              # 进入交互式主菜单"
echo "  elfie serve        # 启动服务"
echo "  elfie --fallback   # 使用内置引擎启动"
echo "  elfie config       # 配置系统"
echo "  elfie status       # 查看状态"
echo "  elfie --help       # 查看帮助"
echo ""

# 创建卸载脚本
cat > "$INSTALL_DIR/uninstall-elfie" << INNER_EOF
#!/bin/bash
rm -f "$INSTALL_DIR/elfie"
rm -f "$INSTALL_DIR/uninstall-elfie"
echo "✅ ElfieNest 已卸载"
INNER_EOF

chmod +x "$INSTALL_DIR/uninstall-elfie"
