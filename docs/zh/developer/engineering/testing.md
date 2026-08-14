# 测试与质量

## 全量门禁的环境预检

启动全仓 pytest 门禁前，先检查当前宿主是否能绑定回环端口：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_environment.py
```

预检不会跳过或降级任何测试，退出码含义如下：

- `0`：允许回环端口绑定，运行一次 `pytest test/`；
- `2`：沙箱或宿主策略拒绝 `127.0.0.1:0`，不要在当前环境运行全量测试，应使用宿主或
  提升权限的环境把同一条全量命令运行一次；
- `1`：预检出现未预期错误，先诊断再启动全量门禁。

网关重启测试仍然属于全量套件。权限拒绝是执行环境结果，不是排除该测试或在单测重试后
再次重跑整套测试的理由。

## 测试层级

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/<changed-module>/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/architecture/
# 仅在上方预检返回 0 后运行。
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/
```

测试目录镜像源码目录。根 `test/` 不直接放测试文件；架构测试负责目录边界、旧包名、
反向依赖和工程配置契约。

## 架构治理检查

```bash
uv run --no-sync python scripts/architecture/app_layer_scan.py \
  --project-root . --mode deny-all
uv run --no-sync python scripts/architecture/system_layer_scan.py \
  --project-root . --mode deny-all
uv run --no-sync pytest test/architecture/
```

App 和系统 Scanner 债务已经清零，两套永久 Scanner 均以 `deny-all` 模式运行，不再使用
旧债基线。未来获批迁移若需要临时精确基线，必须随切片持续缩减并在清零后删除。CI 还会
使用 Pull Request 基础提交中的规则检查候选生产代码，因此同一变更不能放松评判自己的
规则。详见[仓库架构治理契约](../contracts/repository-governance)。

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
