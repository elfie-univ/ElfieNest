# Python代码规范

本规范基于PEP 8、Google Python Style Guide和行业最佳实践制定，适用于ElfieNest项目。

---

## 1. 代码风格规范（PEP 8）

### 1.1 缩进与结构

| 规则 | 标准 |
|------|------|
| 缩进 | 4空格（禁止Tab） |
| 行长度 | 最大88字符（Ruff/Black默认值） |
| 空行 | 类/函数间2行，方法间1行 |
| Import顺序 | 标准库 → 第三方 → 本地模块 |

```python
# 正确示例
import os
import sys
from typing import Any

import numpy as np
from pydantic import BaseModel

from elfie.brain.emotion import EmotionSystem
from elfie.brain.memory import EpisodeManager


class ExampleClass:
    """类文档字符串."""

    def __init__(self, value: int) -> None:
        self.value = value

    def process(self) -> str:
        """处理并返回结果."""
        return f"processed: {self.value}"
```

### 1.2 命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| 模块 | snake_case | `emotion_system.py` |
| 类 | PascalCase | `class EmotionSystem` |
| 函数 | snake_case | `def calculate_decay()` |
| 变量 | snake_case | `emotion_value = 0.5` |
| 常量 | UPPER_SNAKE_CASE | `MAX_ENERGY = 100` |
| 私有属性 | _snake_case | `self._internal_state` |

### 1.3 注释与文档字符串

使用**Google风格**文档字符串：

```python
def calculate_emotion_intensity(
    emotion: str,
    intensity: float,
    decay_rate: float,
) -> float:
    """计算情感的衰减强度。

    根据情感类型和初始强度，计算经过衰减后的实际强度值。

    Args:
        emotion: 情感类型名称（如"joy", "sadness"）
        intensity: 初始强度，范围[0.0, 1.0]
        decay_rate: 衰减率，范围[0.0, 1.0]

    Returns:
        衰减后的强度值，范围[0.0, 1.0]

    Raises:
        ValueError: 当参数超出有效范围时

    Example:
        >>> calculate_emotion_intensity("joy", 1.0, 0.5)
        0.5
    """
    if not 0.0 <= intensity <= 1.0:
        raise ValueError("intensity must be between 0.0 and 1.0")
    return intensity * (1 - decay_rate)
```

---

## 2. 测试规范

### 2.1 测试目录结构决策树

```
是否需要添加测试？
    │
    ├─► 是 → 项目代码还是独立工具？
    │           │
    │           ├─► 项目代码 → 测试放在 test/ 目录
    │           │           (结构镜像应用代码)
    │           │
    │           └─► 独立工具 → 可放在包内 tests/ 或单独仓库
    │
    └─► 否 → 跳过
```

**强制规则**：
- ✅ **推荐**：Tests outside application code（独立`test/`目录）
- ✅ 测试结构应**镜像应用代码结构**
- ✅ 统一使用`test/`目录，**禁止根目录测试文件**
- ✅ **每个测试目录必须有`__init__.py`文件**
- ✅ **测试文件使用绝对导入**（`from elfie.brain.emotion import ...`）

**当前测试结构**（已重组，镜像源代码）：
```
test/
├── __init__.py
├── elfie/
│   ├── __init__.py
│   ├── brain/
│   │   ├── __init__.py
│   │   ├── emotion/
│   │   │   ├── __init__.py
│   │   │   ├── test_emotion_system.py      # 对应 elfie/brain/emotion/emotion_system.py
│   │   │   ├── test_expression_mapper.py   # 对应 elfie/brain/emotion/expression_mapper.py
│   │   │   ├── test_personality.py         # 对应 elfie/brain/emotion/personality.py
│   │   │   ├── test_interactions.py        # 对应 elfie/brain/emotion/interactions.py
│   │   │   └── test_deduplicator.py        # 对应 elfie/brain/emotion/fusion/deduplicator.py
│   │   ├── cognition/
│   │   │   ├── __init__.py
│   │   │   └── test_cognition.py           # 对应 elfie/brain/cognition/*.py
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   └── test_memory.py              # 对应 elfie/brain/memory/*.py
│   │   └── energy/
│   │       ├── __init__.py
│   │       └── test_energy.py              # 对应 elfie/brain/energy/energy.py
│   ├── body/
│   │   ├── __init__.py
│   │   ├── anatomy/
│   │   │   ├── __init__.py
│   │   │   └── test_anatomy.py             # 对应 elfie/body/anatomy/*.py
│   │   └── reflex/
│   │       ├── __init__.py
│   │       └── test_reflex_arc.py          # 对应 elfie/body/reflex/reflex_arc.py
│   ├── interface/
│   │   ├── __init__.py
│   │   ├── actuators/
│   │   │   ├── __init__.py
│   │   │   └── test_actuators.py           # 对应 elfie/interface/actuators/*.py
│   │   └── sensors/
│   │       ├── __init__.py
│   │       └── test_sensors.py             # 对应 elfie/interface/sensors/*.py
│   └── test_embodied_perception.py         # 对应 elfie/elfie_individual.py
├── elfienest/
│   ├── __init__.py
│   ├── test_engine.py                      # 对应 elfienest/engine.py
│   └── test_nest_room.py                   # 对应 elfienest/room.py
└── runtime/
    ├── __init__.py
    └── test_runtime_agent.py               # 对应 runtime/agent.py
```

**新增测试文件的规则**：
1. ✅ **必须放在对应包路径**：例如测试`elfie/brain/emotion/new_feature.py`，测试文件应为`test/elfie/brain/emotion/test_new_feature.py`
2. ✅ **必须创建`__init__.py`**：如果测试目录不存在，创建目录并添加`__init__.py`
3. ✅ **使用绝对导入**：`from elfie.brain.emotion import ...`（不需要相对导入）
4. ❌ **禁止扁平结构**：不要在`test/`根目录直接放置测试文件

### 2.2 "什么时候写测试"决策矩阵

| 场景 | 推荐 | 原因 |
|------|------|------|
| 核心业务逻辑 | ✅ 必须写 | 业务核心，变更影响大 |
| 公共API/接口 | ✅ 必须写 | 外部依赖，稳定保证 |
| 复杂算法/计算 | ✅ 必须写 | 边界情况易出错 |
| 边界情况处理 | ✅ 必须写 | 防止崩溃和数据错误 |
| Bug修复 | ✅ 必须写（回归测试） | 防止再次出现 |
| 装饰器/高阶函数 | ✅ 必须写 | 行为特殊，易被忽略 |
| 简单getter/setter | ❌ 可不写 | 逻辑简单，价值低 |
| 第三方库包装 | ❌ 可不写 | 测试第三方，非本项目 |
| 配置文件 | ❌ 可不写 | 结构简单，验证即可 |
| 临时脚本/一次性代码 | ❌ 可不写 | 无长期维护价值 |
| 原型/实验代码 | ❌ 可不写 | 频繁变更，测试成本高 |

**决策问题**：
1. 这段代码变更会影响核心功能吗？ → 是 → 写测试
2. 其他开发者会调用这段代码吗？ → 是 → 写测试
3. 这段代码有复杂的条件判断吗？ → 是 → 写测试
4. 这是临时/实验性代码吗？ → 是 → 不写

### 2.3 测试命名规范

| 类型 | 规则 | 示例 |
|------|------|------|
| 测试文件 | `test_*.py` | `test_emotion_system.py` |
| 测试函数 | `test_*` | `test_calculate_intensity_returns_expected_value` |
| 测试类 | `Test*` | `class TestEmotionSystem:` |
| Fixtures | `test_*` | `@pytest.fixture def test_user():` |

```python
# 标准测试文件结构
import pytest
from elfie.brain.emotion import EmotionSystem


class TestEmotionSystem:
    """EmotionSystem类的测试套件."""

    @pytest.fixture
    def emotion_system(self) -> EmotionSystem:
        """创建测试用的EmotionSystem实例."""
        return EmotionSystem()

    def test_calculate_intensity_returns_expected_value(
        self,
        emotion_system: EmotionSystem,
    ) -> None:
        """验证强度计算返回预期值."""
        result = emotion_system.calculate_intensity("joy", 1.0, 0.5)
        assert result == 0.5

    def test_calculate_intensity_raises_on_invalid_input(
        self,
        emotion_system: EmotionSystem,
    ) -> None:
        """验证无效输入抛出异常."""
        with pytest.raises(ValueError):
            emotion_system.calculate_intensity("joy", 2.0, 0.5)  # 强度超过1.0
```

### 2.4 测试金字塔

```
        ▲
       /E\        E2E (端到端测试) - 10%
      /---
     /I   \       Integration (集成测试) - 20%
    /-------
   /U       \     Unit (单元测试) - 70%
  /-----------
```

**分层建议**：
- **单元测试（70%）**：独立函数/类/模块的测试
- **集成测试（20%）**：多模块交互、API调用测试
- **E2E测试（10%）**：关键用户路径验证

### 2.5 测试覆盖率要求

| 指标 | 目标 | 说明 |
|------|------|------|
| 总体覆盖率 | ≥ 80% | 必须达到 |
| 关键模块覆盖率 | ≥ 90% | 核心业务逻辑 |
| 新增代码覆盖率 | 100% | 新功能必须完整测试 |

```bash
# 运行覆盖率测试
uv run --no-sync pytest --cov=elfie --cov-report=html --cov-fail-under=80
```

---

## 3. 代码质量工具

### 3.1 Ruff（主要工具）

Ruff = Flake8 + Black + isort + YAPF + ...（超高速Python linter）

开发工具统一由项目锁文件安装，不使用全局 `pip`：

```bash
uv sync --locked --extra dev

# 运行检查
uv run --no-sync ruff check .

# 自动修复
uv run --no-sync ruff check --fix .

# 格式化
uv run --no-sync ruff format .
```

**Ruff配置**（在`pyproject.toml`中）：
```toml
[tool.ruff]
line-length = 88
target-version = "py39"

[tool.ruff.lint]
select = [
    "E",     # pycodestyle errors
    "W",     # pycodestyle warnings
    "F",     # pyflakes
    "I",     # isort
    "B",     # flake8-bugbear
    "C4",    # flake8-comprehensions
    "UP",    # pyupgrade
]
ignore = [
    "E501",  # 行长度由Black处理
]
```

### 3.2 MyPy（类型检查）

**严格模式配置**：
```toml
[tool.mypy]
python_version = "3.9"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

```bash
# 运行类型检查
uv run --no-sync mypy elfie/

# 详细输出
uv run --no-sync mypy --verbose elfie/
```

### 3.3 渐进式改进策略（针对现有77个文件）

由于项目已有77个文件，立即全面严格化不现实。采用**渐进式**策略：

**阶段1：立即生效**
- 新增代码：必须100%类型注解
- 修改的代码：添加类型注解

**阶段2：逐步覆盖**
- 每周选择1-2个模块添加类型注解
- 优先处理：核心业务逻辑（brain/, elfie/）

**阶段3：全面覆盖**
- 覆盖率达标后，开启严格模式检查
- 使用`--strict`逐步迁移

```bash
# 对新文件启用严格检查
uv run --no-sync mypy --strict new_module/

# 对老文件使用宽松配置（逐步收紧）
uv run --no-sync mypy --ignore-missing-imports --no-strict-optional legacy_module/
```

---

## 4. 类型注解策略

### 4.1 严格模式要求

| 规则 | 要求 |
|------|------|
| 函数参数 | 必须有类型注解 |
| 返回值 | 必须有类型注解 |
| 变量 | 建议有类型注解（复杂类型必须） |
| 类属性 | 必须有类型注解 |

```python
# ✅ 正确（严格模式）
def process_data(user_id: int, name: str) -> dict[str, Any]:
    """处理用户数据."""
    result: dict[str, Any] = {"id": user_id, "name": name}
    return result

# ❌ 错误（严格模式不允许）
def process_data(user_id, name):  # 缺少类型注解
    return {"id": user_id, "name": name}
```

### 4.2 复杂类型示例

```python
from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class DataProcessor(Protocol):
    """数据处理协议."""

    def process(self, data: list[dict[str, Any]]) -> list[str]: ...


def transform(
    items: list[int],
    processor: DataProcessor,
    options: dict[str, Any] | None = None,
) -> list[str]:
    """转换数据项."""
    processed = processor.process([{"value": i} for i in items])
    return processed
```

---

## 5. 项目配置文件

### 5.1 pyproject.toml

项目根目录的现代Python项目配置文件：

```toml
[project]
name = "elfienest"
version = "0.1.0"
description = "ElfieNest - Embodied AI creature simulation"
requires-python = "==3.9.25"
dependencies = [
    "websockets>=12.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.1.0",
    "mypy>=1.7.0",
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pre-commit>=3.5.0",
]

[tool.ruff]
line-length = 88
target-version = "py39"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.9"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
testpaths = ["test"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --strict-markers"

[tool.coverage.run]
source = ["elfie", "elfienest", "runtime"]
omit = ["*/test/*", "*/tests/*"]

[tool.coverage.report]
precision = 2
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.:",
    "raise NotImplementedError",
]
fail_under = 80
```

### 5.2 .pre-commit-config.yaml

Git钩子配置，提交前自动检查：

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.0
    hooks:
      - id: mypy
        args: [--strict, --ignore-missing-imports]
```

### 5.3 .github/workflows/ci.yml

GitHub Actions CI/CD工作流：

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2

      - name: Set up uv
        uses: astral-sh/setup-uv@e92bafb6253dcd438e0484186d7669ea7a8ca1cc # v6.4.3
        with:
          version: "0.9.26"

      - name: Install CPython and locked dependencies
        run: |
          uv python install 3.9.25
          uv sync --locked --extra dev

      - name: Run Ruff
        run: uv run --no-sync ruff check . && uv run --no-sync ruff format --check .

      - name: Run MyPy
        run: uv run --no-sync mypy elfie/ elfienest/ runtime/

      - name: Run Tests
        run: uv run --no-sync pytest --cov --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@b9fd7d16f6d7d1b5d2bec1a2887e65ceed900238 # v4.6.0
        with:
          file: ./coverage.xml
```

---

## 6. Git提交规范

### 6.1 Commit Message格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type类型**：
| Type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug修复 |
| `docs` | 文档更新 |
| `style` | 代码格式（不影响功能） |
| `refactor` | 重构（不修复bug不增加功能） |
| `test` | 测试相关 |
| `chore` | 构建/工具链变更 |

**示例**：
```
docs(Python规范): 添加测试目录结构决策树

- 明确测试文件必须放在test/目录
- 添加"什么时候写测试"决策矩阵
- 更新测试金字塔分层建议

Closes #42
```

---

## 7. 检查清单

### 7.1 代码提交前检查

- [ ] `uv run --no-sync ruff check .` 无错误
- [ ] `uv run --no-sync ruff format .` 已格式化
- [ ] `uv run --no-sync mypy <changed_files>` 无错误
- [ ] `uv run --no-sync pytest` 测试通过
- [ ] 覆盖率达标（≥80%）
- [ ] Commit message符合规范

### 7.2 Pull Request检查

- [ ] 所有CI检查通过
- [ ] 代码经过他人审查
- [ ] 无敏感信息泄露
- [ ] 文档已更新（如需要）

---

## 8. 参考资源

### 官方文档
- [PEP 8 - Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [pytest Documentation](https://pytest.org/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [MyPy Documentation](https://mypy.readthedocs.io/)

### 最佳实践
- [Real Python - PEP 8 Tutorial](https://realpython.com/python-pep8/)
- [Python Packaging Guide](https://packaging.python.org/)
- [pre-commit Documentation](https://pre-commit.com/)

---

## 附录：现有问题处理

### A.1 test_deduplicator.py 迁移

**问题**：`test_deduplicator.py`位于项目根目录，违反测试规范

**解决方案**：
```bash
# 移动到test/目录
mv test_deduplicator.py test/test_deduplicator.py
```

**执行时机**：规范文档合并后

### A.2 77个现有文件处理

| 阶段 | 策略 | 目标 |
|------|------|------|
| 立即 | 新代码严格模式 | 新增/修改文件100%类型注解 |
| 1个月 | 核心模块类型化 | brain/ → 90%覆盖 |
| 3个月 | 全面类型化 | 全部模块 → 80%覆盖 |
| 6个月 | 严格模式检查 | 开启mypy --strict |
