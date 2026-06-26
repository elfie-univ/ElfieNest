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

path_contains_dir() {
    local dir="$1"
    [[ ":$PATH:" == *":$dir:"* ]]
}

ensure_writable_dir() {
    local dir="$1"
    mkdir -p "$dir" 2>/dev/null || return 1
    [ -w "$dir" ]
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
