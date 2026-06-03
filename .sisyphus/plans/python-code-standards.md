# Python代码规范文档创建计划

## TL;DR

> **目标**: 创建完整的Python代码规范文档，包括PEP 8、测试规范、代码质量工具等
> 
> **交付物**:
> - `docs/Python代码规范.md` - 完整规范文档
> - `pytest.ini` - pytest配置文件
> - `.flake8` - flake8配置文件
> - `mypy.ini` - mypy配置文件
> 
> **预计工作量**: Quick (单个文档任务)
> **并行执行**: NO (单任务)
> **关键路径**: 研究资料 → 整理规范 → 创建文档 → 创建配置文件

---

## Context

### 原始请求
用户要求查找Python代码规范，特别是：
1. 测试代码是否都应该在test目录下
2. 测试代码是否应该在对应的包里面
3. 什么情况下该加测试，什么情况下不该加测试
4. 其他Python代码规范

### 研究发现

已通过websearch收集以下资料：
1. **PEP 8** - Python官方代码风格指南
2. **Google Python Style Guide** - Google的Python风格指南
3. **pytest最佳实践** - 测试布局和组织规范
4. **代码质量工具** - pylint, flake8, black, mypy

### 关键发现

#### 测试目录结构
- **推荐**: Tests outside application code（独立tests/目录）
- **替代**: Tests as part of application code（内联tests/目录）
- **最佳实践**: 测试结构应镜像应用代码结构

#### 测试命名规范
- 文件: `test_*.py` 或 `*_test.py`
- 函数: `test_*`
- 类: `Test*`

#### 什么时候写测试
**应该写**:
- 核心业务逻辑
- 公共API
- 复杂算法
- 边界情况处理
- Bug修复（回归测试）
- 装饰器

**可以不写**:
- 简单的getter/setter
- 第三方库的简单包装
- 配置文件
- 临时脚本/一次性代码
- 原型/实验代码

---

## Work Objectives

### 核心目标
创建完整的Python代码规范文档，帮助团队遵循统一的编码标准。

### 用户决策
- **类型注解策略**: 严格模式 - 所有新代码和修改的代码都必须有完整类型注解
- **工具选择**: Ruff（现代一站式工具）
- **覆盖率目标**: 80%
- **CI/CD配置**: 包含GitHub Actions工作流

### 具体交付物
1. `docs/Python代码规范.md` - 主文档
2. `pyproject.toml` - 主配置文件（包含black, isort, mypy, pytest, coverage配置）
3. `.pre-commit-config.yaml` - Git hooks配置
4. `.github/workflows/ci.yml` - CI/CD工作流
5. `ruff.toml` - Ruff配置（或集成到pyproject.toml）

### 完成定义
- [ ] 文档包含所有关键规范
- [ ] 文档结构清晰易读
- [ ] 包含具体代码示例
- [ ] 包含"什么时候写测试"的明确指导
- [ ] 配置文件可用

---

## Verification Strategy

### 测试决策
- **基础设施存在**: NO（这是文档任务）
- **自动化测试**: None
- **框架**: None

### QA策略
- 文档内容完整性检查
- 配置文件语法检查
- 示例代码可执行性检查

---

## Execution Strategy

### 单任务执行

```
Task 1: 创建Python代码规范文档 [quick]
├── 整理PEP 8规范
├── 整理测试规范
├── 整理代码质量工具
├── 创建配置文件
└── 验证文档完整性
```

---

## TODOs

- [x] 1. 创建Python代码规范文档

  **What to do**:
  - 创建 `docs/Python代码规范.md`
  - 包含以下章节：
    1. **代码风格规范**（PEP 8）
       - 缩进、行长度、空行
       - 命名规范（模块、类、函数、变量、常量）
       - 注释和文档字符串（Google风格）
       - 类型提示（严格模式要求）
    
    2. **测试规范**（pytest最佳实践）
       - **测试目录结构决策树**（明确回答用户问题）
         - 推荐Tests outside application code
         - 统一使用test/目录，禁止根目录测试文件
         - 测试结构镜像应用代码结构
       - **测试命名规范**
         - 文件: test_*.py
         - 函数: test_*
         - 类: Test*
       - **"什么时候写测试"决策矩阵**（明确回答用户问题）
         - 必须写：核心业务逻辑、公共API、复杂算法、边界情况、Bug修复、装饰器
         - 可以不写：简单getter/setter、第三方库包装、配置文件、临时脚本、原型代码
       - **测试金字塔**：单元70%、集成20%、E2E 10%
       - **测试覆盖率要求**：最低80%
    
    3. **代码质量工具**
       - **Ruff**（主要工具）
         - 替代flake8 + black + isort
         - 配置示例
       - **mypy**（类型检查）
         - 严格模式配置
         - 现有77文件的处理策略
       - **pytest-cov**（覆盖率检查）
    
    4. **项目配置文件**
       - pyproject.toml（主配置）
       - .pre-commit-config.yaml（Git hooks）
       - .github/workflows/ci.yml（CI/CD）
    
    5. **类型注解策略**
       - 新代码：100%类型化
       - 修改的旧代码：添加类型注解
       - mypy严格模式配置
    
    6. **Git提交规范**
       - Commit message格式
       - Type类型（feat, fix, docs等）
    
    7. **检查清单**
       - 代码提交前检查
       - Pull Request检查
    
    8. **参考资源**
  
  - 创建配置文件：
    - `pyproject.toml`（包含black, isort, mypy, pytest, ruff, coverage配置）
    - `.pre-commit-config.yaml`
    - `.github/workflows/ci.yml`
  
  - **重要补充**（根据Metis审查）：
    - 明确处理现有test_deduplicator.py在根目录的问题（应移动到test/）
    - 提供渐进式改进策略（77个现有文件如何处理）

  **Must NOT do**:
  - 不要过于复杂，保持简洁实用
  - 不要推荐立即重构所有77个文件
  - 不要添加不必要的工具配置

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 这是文档整理任务，工作量适中
  - **Skills**: []
    - 无需特殊技能

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: None
  - **Blocked By**: None

  **References**:

  **外部参考资料**:
  - PEP 8: https://peps.python.org/pep-0008/
  - Google Python Style Guide: https://google.github.io/styleguide/pyguide.html
  - pytest最佳实践: https://pytest.org/en/stable/explanation/goodpractices.html
  - Real Python PEP 8教程: https://realpython.com/python-pep8/
  - Ruff官方文档: https://docs.astral.sh/ruff/

  **本地参考**:
  - `elfie/brain/emotion/` - 现有代码风格参考
  - `test/` - 现有测试结构参考
  - `test_deduplicator.py` - 需要移动的测试文件

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: 文档创建成功
    Tool: Bash
    Steps:
      1. 检查文件存在: ls docs/Python代码规范.md
      2. 检查文件大小: wc -l docs/Python代码规范.md
      3. 检查关键章节存在: 
         grep "测试规范" docs/Python代码规范.md
         grep "什么时候写测试" docs/Python代码规范.md
         grep "Ruff" docs/Python代码规范.md
         grep "类型注解策略" docs/Python代码规范.md
    Expected Result: 文件存在且包含所有关键章节
    Evidence: .sisyphus/evidence/task-1-doc-created.txt

  Scenario: 配置文件创建成功
    Tool: Bash
    Steps:
      1. 检查pyproject.toml存在
      2. 检查.pre-commit-config.yaml存在
      3. 检查.github/workflows/ci.yml存在
      4. 验证pyproject.toml包含ruff配置
      5. 验证pyproject.toml包含mypy严格模式配置
    Expected Result: 配置文件存在且配置正确
    Evidence: .sisyphus/evidence/task-1-config-created.txt

  Scenario: 文档内容完整性
    Tool: Bash
    Steps:
      1. 检查包含"测试目录结构决策树"
      2. 检查包含"什么时候写测试决策矩阵"
      3. 检查包含"类型注解严格模式策略"
      4. 检查包含"Ruff配置示例"
      5. 检查包含"CI/CD工作流示例"
    Expected Result: 所有关键内容都存在
    Evidence: .sisyphus/evidence/task-1-content-complete.txt
  ```

  **Evidence to Capture**:
  - [ ] 文档文件创建确认
  - [ ] 配置文件创建确认
  - [ ] 内容完整性检查

  **Commit**: YES
  - Message: `docs: 添加Python代码规范文档和配置文件`
  - Files: `docs/Python代码规范.md`, `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`
  - Pre-commit: None

---

## Final Verification Wave

- [x] F1. **文档完整性检查** — `quick`
  检查文档是否包含所有关键章节，配置文件是否语法正确。
  Output: `章节 [N/N] | 配置 [N/N] | VERDICT: APPROVE`

---

## Commit Strategy

- **1**: `docs: 添加Python代码规范文档和配置文件` - docs/Python代码规范.md, pyproject.toml, .pre-commit-config.yaml, .github/workflows/ci.yml

---

## Success Criteria

### 验证命令
```bash
ls -lh docs/Python代码规范.md  # 文档存在
grep "测试规范" docs/Python代码规范.md  # 包含测试规范章节
grep "什么时候写测试" docs/Python代码规范.md  # 包含决策矩阵
grep "Ruff" docs/Python代码规范.md  # 包含Ruff配置
ls pyproject.toml .pre-commit-config.yaml .github/workflows/ci.yml  # 配置文件存在
```

### 最终检查清单
- [ ] 文档创建成功
- [ ] 包含所有关键章节（测试规范、类型注解策略、Ruff配置、CI/CD）
- [ ] 配置文件创建成功
- [ ] 文档内容准确完整
- [ ] 明确回答了用户的所有问题
