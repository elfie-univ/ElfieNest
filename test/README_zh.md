# ElfieNest 测试

> 中文版：本文件 · [English](README.md)

`test/` 镜像仓库源码边界。测试应放在被测模块对应路径，根目录不得直接新增
`test_*.py`。

## 目录层级

```text
test/
├── ai_runtime/     # 模型、路由、工具、粮食和安全运行时
├── app/            # 产品功能、接口、基础设施与跨模块编排
├── elfie/          # 单个 Elfie 的档案、大脑、神经系统、身体、通信与技能
├── nest/           # 活动空间、状态、互动和 Godot 接口
├── devtools/       # 隔离开发工具
├── godot/          # Godot 场景与资源的静态契约
├── scripts/        # 可测试的仓库脚本逻辑
├── architecture/   # 顶层目录、依赖边界和工程配置契约
├── e2e/            # 跨模块、服务或用户场景
└── support/        # 多个测试域共享的测试辅助代码
```

模块单元测试证明局部行为；`architecture/` 防止目录和依赖边界回退；`e2e/`
验证真实组合链路。不要用端到端测试替代能更快定位问题的单元测试。

## 编写规则

- 行为变化先写会失败的测试，再做最小实现；
- 使用绝对导入，例如 `from elfie.brain import ...`；
- 测试文件命名为 `test_*.py`，测试类命名为 `Test*`，测试函数命名为
  `test_*`；
- 新测试目录应保持与源码相同的职责层级；需要作为 Python 包导入时添加
  `__init__.py`；
- 共享辅助逻辑进入对应模块的 `conftest.py` 或 `test/support/`，不要放在
  根目录测试文件中；
- 不依赖外部生产服务、默认用户目录或真实密钥；涉及文件和数据库时使用临时
  `ELFIE_HOME`。

## 运行

首次准备锁定环境：

```bash
uv sync --locked --extra dev
```

先运行改动直接对应的测试，再运行架构契约：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/elfie/brain/
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/
```

完整测试：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/
```

Pytest 当前声明的 markers：

- `unit`：局部单元测试；
- `integration`：组合多个模块或资源的集成测试；
- `slow`：耗时测试，可用 `-m "not slow"` 排除。

例如：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -m "not slow" test/
```

pytest 缓存、uv 缓存和覆盖率报告都是本地或 CI 产物，不得作为源码提交。质量
基线、pre-commit 和文档构建等完整贡献门见根目录 `CONTRIBUTING_zh.md`。
