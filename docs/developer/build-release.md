# Build & release

## Build directories

```text
build/  reproducible intermediate build artifacts, not committed
dist/   final release artifacts, not committed
docs/.vitepress/dist/  VitePress build output, not committed
```

Generated Godot Web, Desktop JavaScript and Python Core must go into the
corresponding build directory; they are never written back into source
directories.

## Docs site

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
DOCS_BASE=/ npx --yes pnpm@10.12.1 build
```

GitHub Pages uses the `/ElfieNest/` base. Pull Requests only build; only commits
that have been reviewed by the maintainer and merged into `main` may enter the
Pages deploy job.

## Release gate

Before releasing you must confirm:

1. Code, tests and documentation facts agree;
2. Gitleaks, the quality baseline and architecture tests pass;
3. No private worldbuilding, partnership material or unreviewed screenshots are
   on the public pages;
4. The user has completed visual acceptance of the pages;
5. The maintainer then decides when to commit, push and deploy.

## 0.1.0 internal-test desktop installer

We currently build only internal-test installers: the version is pinned to
`0.1.0`, with no auto-update configured, no public Release upload, and no model
weights packaged. Each platform must be built on its corresponding native
runner: macOS ARM64, macOS x64, Windows x64, Linux x64. The Python Core cannot
be cross-faked; the Ollama model is written to `${ELFIE_HOME}/models/` only on
first use.

The release coordinator accepts the full four-target matrix: `darwin-arm64`,
`darwin-x64`, `win32-x64`, and `linux-x64`. Each target must be built on its
matching native runner. When a single machine requests the matrix, it builds
only its local target and reports `requires-native-runner` for the others; it
never fakes a cross-platform artifact. All intermediates live in `build/`, and
final installers only in `dist/`:

发布协调器接受完整四目标矩阵：`darwin-arm64`、`darwin-x64`、`win32-x64`、
`linux-x64`。每个目标必须在对应原生 runner 构建；在一台机器上请求完整矩阵时，
本机目标会构建，其他目标会明确报告 `requires-native-runner`，绝不伪造跨平台产物。
所有中间物都在 `build/`，最终安装包只在 `dist/`：

```bash
# 当前原生目标的完整本地验证，不上传或发布
.venv/bin/python scripts/release.py --target darwin-arm64

# 发布协调：请求完整矩阵并显示仍需原生 runner 的目标
.venv/bin/python scripts/release.py
```

Each installer contains Electron, the frontend, Godot Web, the target-native
Python Core, the management CLI, and a SHA-256-verified target Ollama binary.
Model weights are not packaged; they are written to `${ELFIE_HOME}/models/` on
first use. Source installation with `./install.sh` builds only the current
machine target, then installs the same native application layout as a downloaded
installer; it does not attempt cross-platform builds.

每个安装包包含 Electron、前端、Godot Web、目标原生 Python Core、管理 CLI 和经
SHA-256 校验的目标 Ollama 二进制；模型权重不打包，首次使用时写入
`${ELFIE_HOME}/models/`。源码安装 `./install.sh` 只构建当前机器的目标，再安装到
与下载对应安装包相同的本机应用布局；它不会尝试跨平台构建。

The first internal-test macOS and Windows installers are neither signed nor
notarized, so the system shows an origin warning. This current constraint must
not be bypassed by disabling security mechanisms. Before handoff, installation
tests must record install, launch, `/api/health` success, and no child process
after exit.

首次内测的 macOS、Windows 安装包没有签名或公证，系统会显示来源警告；这是当前
内测约束，不应通过关闭安全机制来绕过。安装测试必须记录“安装、启动、`/api/health`
成功、退出后子进程不存在”四项结果后，才可交给下一位测试者。
