# 开发流程

本页给出从准备环境到完成本地验证的标准开发路径。具体 CLI、Godot 和 Desktop
命令放在[命令与开发工具](./tooling.md)，协作政策以
[贡献指南](https://github.com/elfie-univ/ElfieNest/blob/main/CONTRIBUTING.md)为准。

## 准备锁定环境

项目固定使用 CPython `3.9.25`，依赖以 `uv.lock` 为准：

```bash
./install.sh --env-only
uv sync --locked --extra dev
uv lock --check
```

不要另写一套 `pip install` 流程，也不要修改锁文件来绕过本地环境问题。安装器
只支持用户级安装，不要使用 `root` 或 `sudo`。

## 选择测试层级

测试目录镜像源码边界。先运行离改动最近的测试，再扩大验证范围：

```bash
# 示例：只修改认知协调器
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/elfie/brain/test_coordinator.py

# 所有跨模块或目录边界改动都要运行
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/

# 需要完整回归时
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/
```

`test/architecture/` 防止旧顶层包、非法反向依赖、根级测试文件和工程配置回退。
更完整的目录与 marker 说明见
[测试 README](https://github.com/elfie-univ/ElfieNest/blob/main/test/README.md)。

## 运行质量门

当前仓库有一批被哈希记录的历史 Ruff 与 MyPy 诊断。统一质量门允许历史集合继续
存在，但会阻止任何新增诊断：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_baseline.py

PRE_COMMIT_HOME=/tmp/elfienest-precommit \
  uv run --no-sync pre-commit run --all-files
```

pre-commit 与 CI 还会运行 Gitleaks。不要用 `--no-verify` 绕过密钥检查，也不要为
新问题更新质量基线；应直接修复本次引入的诊断。

## 调试单个模块

三个实验台都与普通用户产品隔离：

```bash
./developer.sh elfie-lab \
  --data-dir /tmp/elfienest-elfie-lab --port 8877

./developer.sh nest-lab \
  --data-dir /tmp/elfienest-nest-lab --port 8890

./developer.sh runtime-lab \
  --config-dir /tmp/elfienest-runtime-lab show
```

- Elfie Lab 检查单精灵档案、感知、决策与回合；
- Nest Lab 检查不依赖正式引擎的 Nest/Godot 模块；
- Runtime Lab 检查 Provider、模型配置和连接，不监听端口。

默认端口只是本地开发值。不要把实验台接入普通用户导航，也不要让它们使用默认
生产数据。详细边界见
[Devtools README](https://github.com/elfie-univ/ElfieNest/blob/main/devtools/README.md)。

## 提交前检查

准备交付一组改动前，至少确认：

1. 改动直接对应的测试通过；
2. `test/architecture/` 通过；
3. 统一质量门和 pre-commit 通过；
4. 改动文档时，VitePress 能完整构建；
5. 没有真实密钥、本机绝对路径、缓存或构建产物；
6. README、架构文档与测试在新增目录或跨边界依赖后保持同步。

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

PR 的范围、测试证据和审阅要求见
[贡献指南](https://github.com/elfie-univ/ElfieNest/blob/main/CONTRIBUTING.md)与
[PR 模板](https://github.com/elfie-univ/ElfieNest/blob/main/.github/pull_request_template.md)。

## 常见问题

### uv 或 Ruff 缓存不可写

把缓存放入临时目录，不要删除仓库或用户数据：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/
```

### 测试读取了日常数据

立即停止测试，并给它设置独立的 `ELFIE_HOME` 或 pytest `tmp_path`。测试、文档
验收和实验台都不应默认读取 `~/.elfienest/`。

### Godot 打不开或版本不一致

先不要打开可编辑项目。阅读
[Godot README](https://github.com/elfie-univ/ElfieNest/blob/main/godot/README.md)，
核对现有 Godot 进程、项目声明版本和 Export Templates，再按公开操作门执行。

### 质量门报告历史问题

先区分 `existing`、`resolved` 和 `new`。只有 `new` 会阻断本次改动；不要通过
写入新基线把它隐藏起来。
