# 测试与质量

## 测试层级

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/<changed-module>/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/architecture/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/
```

测试目录镜像源码目录。根 `test/` 不直接放测试文件；架构测试负责目录边界、旧包名、
反向依赖和工程配置契约。

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
