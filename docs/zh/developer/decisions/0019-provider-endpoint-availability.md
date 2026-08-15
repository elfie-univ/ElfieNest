# ADR-0019：Provider 可用性按 Endpoint 定义并由在用路径驱动

- **状态：** 已接受
- **日期：** 2026-08-15
- **范围：** Provider 清单、Endpoint 能力、验证证据与健康投影

## 背景

Provider 可达性、账号状态、Endpoint 模型可用性和模型能力有不同的失败作用域与刷新频率。
把平台通用 `/models` 当成订阅清单会制造上百个错误候选；把通用模型能力与 Provider 能力
简单组合，会声称某个具体 Provider Endpoint 并未开放的能力。重复验证全部已配置模型会浪费
付费调用，而只验证近期成功模型又可能让已分配但失败的路径退出恢复范围。

Food 定义也有两种范围：全部持久化引用都必须保护删除，但只有可能获得生产流量的 Food
才应该影响定时验证和首页健康。

## 决策

采用以下模型：

- 内置 Provider/模型元数据在 `config/models/` 下只有一份登记来源；产品配置显式选择
  产品专属发现 Authority，平台大清单只作诊断，不进入普通列表；
- 最终能力、请求配置和可用性属于精确 `(connection_id, endpoint_model_id)`；Canonical
  Identity 只能补充显示信息，不能成为最终 Endpoint Authority；
- 全引用保护索引负责删除安全；独立派生的 `ServingFoodIndex` 识别当前生产路由与按角色
  计算的核心模型，在线状态和当前模型健康都不参与成员资格；
- 不可变生产/受控检查观测进入统一读取时可用性投影；被动读取不访问外部，显式主动检查
  感知新鲜度、Single-flight、限流，并按类型化错误分类限定作用域；
- Provider 卡片、首页健康和本地 Ollama 使用同一投影，但 Endpoint 计数与在用角色路径
  摘要保持区分。

规范细节由[模型、Food 与工具行为契约](../contracts/model-food-tool-behavior) 1.8 定义。
当前缺口继续显式记录在
[Provider/模型可用性一致性台账](../conformance/provider-model-availability)。

## 影响

- 账号级失败可以安全复用，不制造虚假的逐模型失败；模型和请求错误保持窄作用域。
- 真实流量以零额外模型调用成本刷新健康，定时工作只覆盖过期的在用核心路径。
- 未上线 Food 引用仍阻止危险删除，但不会让系统健康变黄或消耗验证调用。
- 页面宣称符合前，Endpoint 元数据和证据仍需 Schema 与查询改造；本 ADR 不包含产品实现。
