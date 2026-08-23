# 架构门禁测试规则

本目录是机器架构契约，不是普通单元测试的堆放位置。

- 测试必须对应长期契约中的明确规则，并给出稳定、可诊断的违规位置；禁止用宽泛
  allowlist 掩盖新增债务。
- 历史债务使用精确 baseline，条目只能随生产修复删除。新增规则必须先建立治理变更，
  不能在同一个产品变更中放松扫描器或改写基线。
- 治理提交不得修改旧 Baseline；产品迁移只能删除条目，不能新增、改写或重建。台账
  标记 `closed` 前，对应机器规则的 Baseline 条目必须清零。
- 最后一个债务清零后必须执行独立治理收口：删除空 Baseline、全 closed 台账及其测试
  绑定。全 closed 台账只允许在证据完整且标为 ready 时短暂等待独立治理删除；空
  Baseline 始终拒绝。删除测试必须从基线注册表与台账取证，不能只看候选分支。
- 清理完成门禁必须同时攻击“只跑测试便宣布完成”“未盘点目录”“临时路径新增文件”与
  “连同注册项提前删除台账”；结构 Scanner 还要用未知目录 Fixture 证明 fail-closed。
- 变更分类攻击测试必须覆盖全仓实现表面，不得只用 `app/` 或某个当前违规目录举例。
  `devtools/`、普通脚本、根入口、普通测试、Manifest、文档站代码和 Workflow 至少各有
  一个代表用例；同时证明架构 Scanner/测试的治理身份优先、普通说明文档保持中立。
- Scanner 按职责放在 `scripts/governance/`，验证选择与证据复用位于
  `scripts/quality/`，供本地测试和 CI 复用；测试验证扫描算法、契约
  路径、临时债务生命周期和主分支 ratchet。
- `test_app_layer_boundaries.py` 约束 App 内部分层；`test_system_layer_boundaries.py`
  约束 `app`、`elfie`、`nest`、目标 `infrastructure` 之间的系统级边界。两套规则
  可以嵌套，但不得互相替代。
- `test_effective_dependency_boundaries.py` 必须同时攻击模块命令、脚本路径、动态加载、
  Node 子进程、Godot、Shell 与未知源码根目标，并跨 Interface、Feature、Core、
  Infrastructure、Bootstrap、Scripts 与 Developer Tools 所有权验证允许和禁止方向。
- 删除或弱化规则属于治理变更，必须同步 ADR/契约并与实现侧文件分开审查。
- 只运行与本次边界变化直接相关的架构测试；不得把产品功能断言塞进本目录。
