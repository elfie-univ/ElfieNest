# 测试与质量

## 测试层级

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/<changed-module>/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/architecture/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/
```

测试目录镜像源码目录。根 `test/` 不直接放测试文件；架构测试负责目录边界、旧包名、
反向依赖和工程配置契约。

## 架构治理检查

```bash
uv run --no-sync python scripts/architecture/app_layer_scan.py \
  --project-root . --baseline test/architecture/baselines/app_layer.py --mode exact
uv run --no-sync python scripts/architecture/system_layer_scan.py \
  --project-root . --baseline test/architecture/baselines/system_layer.py --mode exact
uv run --no-sync pytest test/architecture/
```

基线只列出精确的既有违规，不授权新代码复制旧债。迁移删除旧调用链时，同步删除对应
基线条目；基线清零后直接删除，并让同一 Scanner 以 `--mode deny-all` 永久运行。CI 还会
使用 Pull Request 基础提交中的 Scanner 和基线检查候选生产代码，因此同一变更不能放松
评判自己的规则。详见[仓库架构治理契约](../contracts/repository-governance)。

## 质量门

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync python scripts/check_quality_baseline.py
PRE_COMMIT_HOME=/tmp/elfienest-precommit uv run --no-sync pre-commit run --all-files
```

质量基线只容纳已经存在的诊断；新增 Ruff、格式或 MyPy 诊断必须修复，不通过扩大
忽略项或改写基线隐藏。

## 文档验证

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

页面还需要检查导航、内部链接、移动布局和浏览器控制台。
