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
| PMA-001 | P0 | in progress | 通用/精选发现已经有边界，远程目录也会在没有完整性固定值时安全拒绝；但所有 `provider_adapter` 产品还没有具体官方 Adapter，来源管理模型还没有面向用户的事务性清理动作。 | 补齐所需官方 Adapter；增加清理命令，并在删除事务内重新检查全部引用、30 天缺失和生产使用条件。 | `infrastructure/models/validation/provider_validation.py`、`infrastructure/models/providers/discovery.py`、`infrastructure/models/providers/remote_catalog.py` |
| PMA-002 | P0 | in progress | Endpoint 级能力声明、证据等级和 Request Profile 已实现；视觉/工具/推理/结构化输出的无副作用受控探测及 verified 证据升级尚未实现。 | 增加按通道的受控探测，保存 verified/unsupported 证据，不能把文本成功当成其他能力证明。 | `infrastructure/models/provider_records.py`、`infrastructure/models/providers/endpoint_capabilities.py`、`infrastructure/models/providers/request_profiles.py` |
| PMA-003 | P0 | in progress | 生产/验证观测、指纹、读取时投影和查询 Port 已实现；独立的 5 分钟连通性证据流以及有界保留/汇总尚未实现。 | 增加 transport/auth 观测和 5 分钟新鲜度，同时保留精确 Endpoint 证据。 | `infrastructure/models/model_execution_observations.py`、`infrastructure/persistence/provider_availability.py`、`infrastructure/models/validation/provider_availability.py` |
| PMA-004 | P0 | in progress | `ServingFoodIndex` 已实现分配/默认/Emergency/直接使用、24 小时/30 天角色窗口和 Endpoint 去重；可选必需角色策略还没有持久化/暴露，队列任务取消也未实现。 | 持久化必需角色策略，Food 变化递增投影 generation，并取消不再属于核心集的任务。 | `infrastructure/models/validation/serving_food.py`、`app/bootstrap/container.py`、`app/features/configuration/food/port_models.py` |
| PMA-005 | P0 | in progress | 类型化错误作用域、账号级提前停止、瞬态迟滞、跨模型传输故障提升、有界并发、Single-flight 和冷却已实现；跨进程调度租约和周期性核心验证 Worker 尚未实现。 | 增加一个带租约的调度入口，只验证到期的核心 Endpoint/能力通道。 | `infrastructure/models/provider_errors.py`、`infrastructure/models/validation/provider_validation_runs.py`、`infrastructure/persistence/provider_availability.py` |
| PMA-006 | P1 | in progress | 卡片底色/徽章、有限摘要、首页核心路径过滤和本地服务/模型门禁已实现；过期模型视图/清理 UI 以及真实 Provider/浏览器验收证据尚未完成。 | 增加过期模型管理界面，并在凭据脱离代码注入后记录一次实际 served checkout/browser 验收。 | `app/interfaces/web/frontend/src/components/OwnerProviderPanel.tsx`、`app/interfaces/web/frontend/src/components/ManageMonitorPanel.tsx`、`app/interfaces/web/frontend/src/components/OwnerOllamaPanel.tsx` |

## 收口顺序

1. 完成官方发现/清理和 Endpoint 能力证据。
2. 增加传输证据和持久化的 Serving 角色策略。
3. 增加带租约的核心集调度和保留策略。
4. 完成过期模型 UI 与真实浏览器验收。

在每一行都有 `target`、`inventory`、`references`、`verification`、`residuals` 五类证据，
且永久行为、架构和浏览器门禁保持 deny-all 之前，本台账保持开放。
