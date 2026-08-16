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
- 内置 OpenAI 兼容/API 产品读取经过认证的实时模型清单。小型内置列表标记默认展示的
  核心模型；完整权威接口返回的其他 ID 会保留为隐藏的“其他已发现”模型，用户可以一键
  启用，不需要重新输入每个模型。Coding Plan 等仅目录产品继续使用明确的产品清单，
  不把宽泛平台目录当成套餐权益。
- Endpoint 记录保存连接级上下文/输出限制、能力声明、能力证据和类型化 Request
  Profile ID/版本。动态健康来自追加式观测，不写回 Provider 模型配置；生产调用和验证
  使用同一个规范配置指纹。
- App 已接入精确 Endpoint 的被动查询、有界批量读取、受权限保护的主动检查、进程内
  Single-flight 和冷却。Serving 投影会排除未使用 Food 和未激活可选角色，Provider 卡片、
  首页 Monitor 和 Ollama 页面使用同一套门禁。
- 能力探测按 Endpoint 和通道执行。工具、视觉、推理和结构化输出证据与文本健康分开保存，
  只有实际观测到的功能使用才能把证据提升为 verified。
- Provider 连通性拥有独立的 5 分钟投影，不消耗模型生成 token。核心模型检查通过 SQLite
  跨进程租约调度；只有当前 `ServingFoodIndex` 中的 Endpoint 才进入周期性模型验证队列。
- 来源缺失模型不进入正常模型列表，并提供仅 Owner 可见的过期模型列表和受保护清理动作。
  清理前会重新检查来源缺失/生产使用时限和全部 Food 引用。
- 报告仓库提供受保护的日汇总和保留策略：普通调用方不能修改观测，显式维护任务只在已
  完成的运行上汇总并删除旧观测，且不保存 prompt/response 内容。
- 调度运行记录 `ServingFoodIndex` generation；如果 Food/模型配置在运行中变化，就放弃
  剩余旧快照，下一轮使用新 generation。
- Ollama 必须同时满足服务健康、精确模型已安装且模型可用；安装、启动修复和模型下载
  仍然是显式操作。

## 开放缺口

| ID | 严重度 | 状态 | 剩余偏差 | 收口门 | 证据 |
| --- | --- | --- | --- | --- | --- |
| PMA-001 | P0 | partial | 实时 `/models` 发现、核心/其他模型分层、一键启用和两次刷新过期保留已实现。仅目录产品使用明确清单；非通用的 Provider 仍需要产品专用 Adapter，删除仍是 Owner 的显式动作。 | 只补充仍需要的非通用发现 Adapter，并在 30 天/引用门禁满足后实际走一次受保护清理。 | `infrastructure/models/validation/provider_validation.py`、`infrastructure/models/providers/discovery.py`、`infrastructure/models/provider_administration.py`、`app/interfaces/web/frontend/src/components/ProviderModelsDialog.tsx` |
| PMA-002 | P0 | partial | Endpoint 级受控探测、语义 Request Profile 映射和按通道的证据升级已实现；所有支持 Provider Adapter 的真实验收仍未完成。 | 使用脱离代码注入的凭据运行真实 Provider 能力矩阵，并关闭 Adapter 特有的探测缺口。 | `infrastructure/models/validation/provider_capability_probes.py`、`infrastructure/models/provider_administration.py`、`app/interfaces/api/v1/admin/model_providers/routes.py` |
| PMA-003 | P0 | partial | 生产/验证观测与独立的 5 分钟 transport/auth 证据流、读取时投影、有界原始保留和日汇总已实现；长期运行验收仍未完成。 | 在长时间运行安装中验证保留/汇总，包括重启和迟到观测边界。 | `infrastructure/models/validation/provider_validation_checks.py`、`infrastructure/models/validation/provider_availability.py`、`infrastructure/models/validation/provider_scheduler.py`、`infrastructure/persistence/reports/report_repository.py`、`infrastructure/persistence/reports/report_schema.py` |
| PMA-004 | P0 | partial | `ServingFoodIndex` 已实现分配/默认/Emergency/直接使用、24 小时/30 天角色窗口、Endpoint 去重、required-role 策略持久化、generation 变化和过时任务取消。 | 在运行中的安装里验证 Food 编辑会让进行中的 generation 失效。 | `infrastructure/models/validation/serving_food.py`、`infrastructure/models/validation/provider_scheduler.py`、`app/bootstrap/container.py`、`app/features/configuration/food/models.py`、`app/interfaces/web/frontend/src/components/FoodRecipeEditor.tsx` |
| PMA-005 | P0 | partial | 类型化错误作用域、账号级提前停止、瞬态迟滞、跨模型传输故障提升、有界并发、Single-flight/冷却、SQLite 租约、generation 取消、周期性核心验证和租约保护的保留维护已实现；真实多进程运行证据仍未完成。 | 使用同一个报告数据库运行两个 Worker，验证每个租约验证/保留任务只有一个 Worker 执行。 | `infrastructure/models/validation/provider_scheduler.py`、`infrastructure/persistence/reports/report_repository.py`、`app/bootstrap/container.py` |
| PMA-006 | P1 | partial | 卡片底色/徽章语义、有限摘要、首页核心路径过滤、本地服务/模型门禁、过期模型检查和受保护清理 UI 已实现；真实 Provider/浏览器验收证据仍未完成。 | 使用脱离代码注入的真实凭据记录一次 served checkout/browser 验收。 | `app/interfaces/web/frontend/src/components/ProviderModelsDialog.tsx`、`app/interfaces/api/v1/admin/model_providers/routes.py`、`app/interfaces/web/frontend/src/api/owner-providers.ts` |

## 收口顺序

1. 只补充剩余的非通用发现 Adapter，并收集 Endpoint 能力证据。
2. 记录真实的多进程、长期保留和 Provider/浏览器验收证据。

在每一行都有 `target`、`inventory`、`references`、`verification`、`residuals` 五类证据，
且永久行为、架构和浏览器门禁保持 deny-all 之前，本台账保持开放。
