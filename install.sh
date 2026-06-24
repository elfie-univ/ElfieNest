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

# 检测安装位置
if [ "$EUID" -eq 0 ]; then
    INSTALL_DIR="/usr/local/bin"
    echo "📦 安装模式: 系统安装 (需要 root 权限)"
else
    INSTALL_DIR="$HOME/bin"
    echo "📦 安装模式: 用户安装"
fi

echo "📍 安装位置: $INSTALL_DIR"
echo ""

# 创建目录
mkdir -p "$INSTALL_DIR"

# 创建 elfie 命令（指向 elfie.sh）
cat > "$INSTALL_DIR/elfie" << INNER_EOF
#!/bin/bash
cd "$PROJECT_ROOT"
./elfie.sh "\$@"
INNER_EOF

chmod +x "$INSTALL_DIR/elfie"

echo "✅ 已安装 elfie 命令"
echo ""

# 检查 PATH
if [ "$EUID" -ne 0 ]; then
    if [[ ":$PATH:" != *":$HOME/bin:"* ]]; then
        echo "⚠️  ~/bin 不在 PATH 中"
        echo ""
        echo "请添加以下内容到 ~/.zshrc 或 ~/.bashrc:"
        echo '    export PATH="$HOME/bin:$PATH"'
        echo ""
        echo "然后执行:"
        echo "    source ~/.zshrc"
        echo ""
    fi
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
