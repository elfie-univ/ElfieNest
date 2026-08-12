# ADR-0012：有效依赖包含动态执行目标

**状态：** 已接受
**日期：** 2026-08-12

## 背景

过去的架构 Scanner 只把 Python import 视为依赖边。产品入口因此可以使用
`python -m` 或脚本路径启动被禁止的仓库模块，在没有 import 的情况下绕过同一边界。
动态加载器、Node 子进程和 Shell 命令也存在同类缺口。若只针对本次暴露问题的模块写
规则，下一个禁止目标仍会漏过，而且无法表达架构契约本身。

## 决策

能够从 Python、Node、Godot 或 Shell 执行表面解析出的仓库模块目标，都属于有效依赖，并遵守
与静态 import 相同的“调用方所有者到目标所有者”矩阵。

因此，`scripts/architecture/effective_dependency_scan.py`：

- 在全仓按调用方和目标的架构所有者分类，不为某个目录写黑名单；
- 检测字面量 Python 模块命令、仓库脚本路径、`importlib`/`runpy`、Node 动态加载与
  子进程调用、Godot 进程调用以及 Shell 模块/脚本命令；未知源码根默认拒绝；
- 忽略外部可执行程序名，因为它们是技术依赖，不是仓库模块依赖边；
- 不建立历史基线，拒绝全部禁止的有效依赖；
- 在候选代码上直接执行；本治理变更进入基础分支后，CI 还必须使用基础提交中的不可变
  Scanner 检查候选代码。

无法静态解析的间接启动计划不因此自动获准。产品层通过窄 Port 接收，具体计划由
Bootstrap 或拥有该能力的 Infrastructure Adapter 构造，并继续接受语义人工审查。

## 后果

把禁止目标从 import 移进命令字符串，不能再改变依赖判定。Interface 继续只调用公开
Feature 或 Orchestration 边界；Developer Tools 可以为了隔离实验使用产品公开边界，
但生产根目录和产品入口脚本不得启动 Developer Tools。Fixture 会攻击多个调用方和目标
所有者，避免门禁退化成一次性的 `devtools` 检查。

本决策只扩展冻结架构的执行方式，不改变顶层所有权、authority、Port 语义或宏观架构
基线。
