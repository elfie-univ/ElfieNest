# Provider/模型可用性一致性

> 本文是规范性[模型、Food 与工具行为契约](../contracts/model-food-tool-behavior) 1.8 的
> 开放迁移台账，只记录当前实现事实和剩余删除门，不削弱已经确认的可用性设计。

**状态：** partial

## 当前已符合的事实

- Provider 产品、连接、精确 Endpoint 模型、报告证据、引用保护和派生
  `ServingFoodIndex` 是分开的事实层。
- 火山引擎 Coding Plan 使用 `catalog_only`，当前只暴露精选的 8 个 Coding Plan
  模型 ID，不会把宽泛的 `/models` 清单带进正常订阅列表。通用发现有响应边界，拒绝
  不完整分页，保留权威空结果，并把遗漏模型保留为 `source_missing`，不会直接删除。
- Endpoint 记录保存连接级上下文/输出限制、能力声明、能力证据和类型化 Request
  Profile ID/版本。动态健康来自追加式观测，不写回 Provider 模型配置；生产调用和验证
  使用同一个规范配置指纹。
- App 已接入精确 Endpoint 的被动查询、有界批量读取、受权限保护的主动检查、进程内
  Single-flight 和冷却。Serving 投影会排除未使用 Food 和未激活可选角色，Provider 卡片、
  首页 Monitor 和 Ollama 页面使用同一套门禁。
- Ollama 必须同时满足服务健康、精确模型已安装且模型可用；安装、启动修复和模型下载
  仍然是显式操作。

## 开放缺口

| ID | 严重度 | 状态 | 剩余偏差 | 收口门 | 证据 |
| --- | --- | --- | --- | --- | --- |
| PMA-001 | P0 | in progress | 通用/精选发现有边界，远程目录在没有完整性固定值时安全拒绝；当前内置产品没有使用 `provider_adapter`，来源管理模型已有显式清理动作，并在一次替换前重新检查引用和 30 天生产使用条件。 | 任何产品声明 `provider_adapter` 时补齐其官方 Adapter；用户管理界面另由 PMA-006 收敛。 | `infrastructure/models/validation/provider_validation.py`、`infrastructure/models/providers/discovery.py`、`infrastructure/models/providers/remote_catalog.py`、`app/features/configuration/providers/service.py` |
| PMA-002 | P0 | in progress | Endpoint 级能力声明、证据等级、Request Profile 以及视觉/工具/推理/结构化输出的无副作用受控探测已实现；能力证据独立持久化且最新证据优先。 | 对所有支持的真实 Provider Profile 验证探测和 fingerprint 失效行为。 | `infrastructure/models/provider_records.py`、`infrastructure/models/providers/endpoint_capabilities.py`、`infrastructure/models/providers/request_profiles.py`、`infrastructure/models/validation/capability_probes.py` |
| PMA-003 | P0 | in progress | 生产/验证观测、指纹、读取时投影和独立的 5 分钟连通性证据流已实现；有界保留/汇总和真实传输验收仍缺。 | 在不破坏 append-only 证据的前提下增加保留/汇总策略，再运行真实 transport/auth 验收。 | `infrastructure/models/model_execution_observations.py`、`infrastructure/persistence/provider_availability.py`、`infrastructure/models/validation/provider_availability.py`、`infrastructure/models/validation/provider_validation_runs.py` |
| PMA-004 | P0 | in progress | `ServingFoodIndex` 已实现分配/默认/Emergency/直接使用、24 小时/30 天角色窗口、Endpoint 去重、持久化 required-role 策略、generation 变化和过时队列任务取消。 | 证明所有 Food 写路径刷新同一 generation，运行中的 Core 不会执行过时任务。 | `infrastructure/models/validation/serving_food.py`、`app/bootstrap/container.py`、`app/features/configuration/food/port_models.py`、`infrastructure/models/validation/core_validation_scheduler.py` |
| PMA-005 | P0 | in progress | 类型化错误作用域、账号级提前停止、瞬态迟滞、跨模型传输故障提升、有界并发、Single-flight/冷却、跨进程租约和周期性 Core-only Worker 已实现。 | 运行多进程、崩溃/重启验收，并证明 Worker 停止不会阻塞 Core 关闭。 | `infrastructure/models/provider_errors.py`、`infrastructure/models/validation/provider_validation_runs.py`、`infrastructure/models/validation/core_validation_scheduler.py`、`infrastructure/models/validation/core_validation_worker.py` |
| PMA-006 | P1 | in progress | 卡片底色/徽章、有限摘要、首页核心路径过滤和本地服务/模型门禁已实现；过期模型视图/清理 UI 以及真实 Provider/浏览器验收证据尚未完成。 | 增加过期模型管理界面，并在凭据脱离代码注入后记录一次实际 served checkout/browser 验收。 | `app/interfaces/web/frontend/src/components/OwnerProviderPanel.tsx`、`app/interfaces/web/frontend/src/components/ManageMonitorPanel.tsx`、`app/interfaces/web/frontend/src/components/OwnerOllamaPanel.tsx` |

## 收口顺序

1. 在不削弱 append-only 证据的前提下增加保留/汇总策略。
2. 完成跨平台/Core Worker 以及真实 Provider 能力/传输验收。
3. 完成过期模型 UI 与真实浏览器验收。

在每一行都有 `target`、`inventory`、`references`、`verification`、`residuals` 五类证据，
且永久行为、架构和浏览器门禁保持 deny-all 之前，本台账保持开放。
