# Provider/模型可用性一致性

> 本文是规范性[模型、Food 与工具行为契约](../contracts/model-food-tool-behavior) 1.8 的
> 开放迁移台账，只记录当前实现事实和剩余删除门，不削弱已经确认的可用性设计。

**状态：** in progress

## 当前已符合的事实

- Provider 产品、连接、精确 Endpoint 模型、报告证据、引用保护和派生
  `ServingFoodIndex` 是分开的事实层。
- 火山引擎 Coding Plan 使用产品专用 Adapter，从 `/api/coding` 网关下订阅级的
  `/models` 清单读取模型。内置的 8 个 ID 只是产品维护的核心/回退推荐，不代表账号权益。
  Adapter 有响应边界，拒绝不完整分页，保留权威空结果，并把遗漏模型保留为
  `source_missing`，不会直接删除。
- 内置 OpenAI 兼容/API 产品读取经过认证的实时模型清单。小型内置列表标记默认展示的
  核心模型；完整权威接口返回的其他 ID 会保留为隐藏的“其他已发现”模型，用户可以一键
  启用，不需要重新输入每个模型。只要宽泛平台清单不是产品权益来源，就必须使用产品
  专用 Adapter。
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

## Conformance rows

标记为 `closed` 的行保留作为本次迁移的审计证据；仍为 `in progress` 的行才是当前未闭合项。

| ID | 严重度 | 状态 | 剩余偏差 | 收口门 | 证据 |
| --- | --- | --- | --- | --- | --- |
| PMA-001 | P0 | in progress | 实时 `/models` 发现、核心/其他模型分层、一键启用、火山引擎 Coding Plan 产品 Adapter 和两次刷新过期保留已实现。删除仍是 Owner 的显式动作。 | 在 30 天/引用门禁满足后实际走一次受保护清理。 | `infrastructure/models/validation/provider_validation.py`、`infrastructure/models/providers/discovery.py`、`infrastructure/models/provider_administration.py`、`app/interfaces/web/frontend/src/components/ProviderModelsDialog.tsx` |
| PMA-002 | P0 | closed | Endpoint 级受控探测、语义 Request Profile 映射和按通道的证据升级已实现。当前配置且实际使用的火山引擎 Coding Plan 作为本次发布的代表远程 Provider，已完成 8 个模型的真实文本验证，以及每个 Endpoint 的工具/视觉/推理探测。未配置的 Adapter 延后到实际配置并使用时再进入验收。 | 每次发布至少对一个已配置且实际使用的远程 Provider 代表执行真实能力矩阵并记录 Adapter 特有缺口；其他 Adapter 配置并投入使用后再纳入范围。 | target=代表远程 Provider 能力矩阵；inventory=8 个已配置的火山引擎 Coding Plan Endpoint 模型及工具/视觉/推理通道；references=`infrastructure/models/validation/provider_capability_probes.py`、`infrastructure/models/provider_administration.py`；verification=`$ELFIE_HOME/reports/ai-runtime.sqlite` 中真实运行 `run_81c08bccaf6e41d69ced2114d5fcb715`；residuals=未配置且未实际使用的 Adapter 延后 |
| PMA-003 | P0 | in progress | 生产/验证观测与独立的 5 分钟 transport/auth 证据流、读取时投影、有界原始保留和日汇总已实现；长期运行验收仍未完成。 | 在长时间运行安装中验证保留/汇总，包括重启和迟到观测边界。 | `infrastructure/models/validation/provider_validation_checks.py`、`infrastructure/models/validation/provider_availability.py`、`infrastructure/models/validation/provider_scheduler.py`、`infrastructure/persistence/reports/report_repository.py`、`infrastructure/persistence/reports/report_schema.py` |
| PMA-004 | P0 | closed | `ServingFoodIndex` 已实现分配/默认/Emergency/直接使用、24 小时/30 天角色窗口、Endpoint 去重、required-role 策略持久化、generation 变化和过时任务取消。 | 可重放运行场景在验证进行中修改 serving Food，取消全部旧 generation 的排队通道，并验证下一代。 | target=serving Food generation 失效；inventory=Food 分配/默认/Emergency/直接使用角色、required-role 策略、generation 和排队验证通道；references=`infrastructure/models/validation/serving_food.py`、`infrastructure/models/validation/core_validation_scheduler.py`、`infrastructure/models/validation/provider_scheduler.py`；verification=`test/infrastructure/models/validation/test_core_validation_scheduler.py` 的重放场景；residuals=none |
| PMA-005 | P0 | closed | 类型化错误作用域、账号级提前停止、瞬态迟滞、跨模型传输故障提升、有界并发、Single-flight/冷却、SQLite 租约、generation 取消、周期性核心验证和租约保护的保留维护已实现。 | 两个独立 POSIX Worker 共用一个报告数据库；模型验证和保留任务各自都只有一个 Worker 执行。 | target=单飞行与跨进程验证/保留租约；inventory=类型化错误、账号提前停止、迟滞、冷却、generation 取消、Worker 和 SQLite 租约路径；references=`infrastructure/models/validation/provider_scheduler.py`、`infrastructure/persistence/reports/report_repository.py`；verification=`test/infrastructure/models/validation/test_provider_scheduler.py` 的多进程租约场景；residuals=none |
| PMA-006 | P1 | in progress | 卡片底色/徽章语义、有限摘要、首页核心路径过滤、本地服务/模型门禁、过期模型检查和受保护清理 UI 已实现；真实 Provider/浏览器验收证据仍未完成。 | 使用脱离代码注入的真实凭据记录一次 served checkout/browser 验收。 | `app/interfaces/web/frontend/src/components/ProviderModelsDialog.tsx`、`app/interfaces/api/v1/admin/model_providers/routes.py`、`app/interfaces/web/frontend/src/api/owner-providers.ts` |

## 收口顺序

1. 只补充剩余的非通用发现 Adapter，并收集 Endpoint 能力证据。
2. 记录长期保留和 Provider/浏览器验收证据。
3. PMA-002 本次发布使用当前已配置且实际使用的远程 Provider 作为代表；其他 Adapter 配置并投入使用后再进入门禁。
4. PMA-004 和 PMA-005 已由当前 generation 失效及多进程租约可重放场景关闭。

在每一行都有 `target`、`inventory`、`references`、`verification`、`residuals` 五类证据，
且永久行为、架构和浏览器门禁保持 deny-all 之前，本台账保持开放。
