# 构建与发布

## 构建目录

```text
build/  可再生中间构建产物，不提交
dist/   最终发行物，不提交
docs/.vitepress/dist/  VitePress 构建产物，不提交
```

Godot Web、Desktop JavaScript 和 Python Core 的生成结果必须进入对应构建目录，不
写回源码目录。

## 文档站

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
DOCS_BASE=/ npx --yes pnpm@10.12.1 build
```

GitHub Pages 使用 `/ElfieNest/` base。Pull Request 只构建；只有经过负责人审阅并
进入 `main` 的提交才允许进入 Pages 部署 job。

## 发布门

发布前必须确认：

1. 代码、测试和文档事实一致；
2. Gitleaks、质量基线和架构测试通过；
3. 公开页面没有私有世界观、合作材料和未审阅截图；
4. 用户完成页面目视验收；
5. 再由负责人决定何时提交、推送和部署。

## 0.1.0 内测桌面安装包

当前只构建内部测试安装包：版本固定为 `0.1.0`，不配置自动更新、不上传公开
Release，也不打包任何模型权重。每个平台必须在对应原生 runner 上构建：macOS
ARM64、macOS x64、Windows x64、Linux x64。Python Core 不能跨平台伪造，Ollama
模型首次使用时才写入 `${ELFIE_HOME}/models/`。

构建顺序如下；所有中间物都在 `build/`，最终安装包只在 `dist/`：

```bash
# 1. 产品前端
cd app/interfaces/web/frontend
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
cd ../../../..

# 2. 在当前目标平台冻结 Python Core
uv sync --locked --extra release
.venv/bin/python scripts/package_python_core.py freeze-core \
  --target darwin-arm64 --output-dir build/python-core/darwin-arm64

# 3. 导出 Godot Web（使用项目要求的 Godot 4.7 和 Web Export Templates）
python3 scripts/build_godot_web.py

# 4. 下载与清单中版本、SHA-256 对应的 Ollama archive 后，组装单 target staging
.venv/bin/python scripts/assemble_desktop_resources.py \
  --target darwin-arm64 \
  --ollama-archive build/downloads/ollama/darwin-arm64/ollama-darwin.tgz

# 5. 只生成当前 target 的 unsigned internal installer
cd desktop
ELFIENEST_TARGET=darwin-arm64 \
  npx --yes pnpm@10.12.1 exec electron-builder --mac --arm64 --publish never
```

首次内测的 macOS、Windows 安装包没有签名或公证，系统会显示来源警告；这是当前
内测约束，不应通过关闭安全机制来绕过。安装测试必须记录“安装、启动、`/api/health`
成功、退出后子进程不存在”四项结果后，才可交给下一位测试者。
