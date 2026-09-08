# ADR-0037：单一类型化 Brain 观测表面与唯一 sink Port

- **状态：** accepted
- **日期：** 2026-09-08
- **范围：** Elfie Brain、Elfie 装配与开发者工具

## 背景

Brain 边界此前通过两个临时 dict 回调（`memory_observer`、`context_observer`）把进展
上报给开发者工具，并经 `Elfie.configure_cognition` 接线。这些事件没有共享封套、没有
公共生命周期字段、也没有稳定的边界分类；每个消费者各自解析自己的 dict 形状，没有人
监听时生产路径仍然构造事件 dict，而每个开发者工具都自造一条采集路径。这改变了组合根
注入 Brain 聚合的内容，因此需要一项决策。

## 决策

- Brain 拥有一个强类型出站观测 Port：`BrainObservationSink`（带 `emit`/`snapshot`
  的 Protocol）、不可变 `BrainObservation` 封套和 `NoOpSink`，全部定义在
  `elfie/brain/observation.py`。装配通过
  `Elfie.configure_cognition(observation_sink=...)` 最多注入一个可选 sink，并由
  `assemble_brain_runtime` 分发给各个持有者；Brain 不定义第二套观察回调。
- 每个可观测边界发出的封套，其 `payload` 都是该边界组自有的命名 frozen model，放在
  专属 payload 模块中：`elfie/brain/reasoning/observation_payloads.py`、
  `elfie/brain/reasoning/agent_loop_observations.py`、
  `elfie/brain/reasoning/run_controller_observations.py`、
  `elfie/brain/reasoning/coordinator_observations.py`、
  `elfie/brain/activity/observation_payloads.py` 和
  `elfie/brain/memory/observation_payloads.py`。这些模块固定边界分类；payload
  永远不是 `Any` 或裸 dict。
- 发射点在构造封套前先判断 `sink is not None`（先守卫再构造）：未接 sink
  的生产路径零分配开销。`test/elfie/test_observation_zero_cost.py` 锁定该规则。
- 观测绝不影响 Brain 行为：`emit` 不抛异常，采集失败留在 sink 内部。
- 开发者工具（Elfie Lab、Brain 评估与 Brain 链路采集）通过实现或包装 sink 消费该
  表面；它们不增加第二条 Brain 回调路径，也不维护磁盘 JSON Schema——Pydantic
  模型仍是唯一契约事实源。
- Infrastructure 的模型执行观测保持独立（遵循 ADR-0002）：模型 Endpoint 观测是能力面
  的事实来源，不并入也不实现 Brain 观测表面。

## 后果

一条强类型管线取代两个 dict 回调，所有开发者工具读取同一批记录。Brain 契约记录该
Port 与 payload 模块（版本 1.10）。架构测试保持观测模块领域纯净——不导入
`infrastructure`、`app`、`nest` 或 `devtools`，不使用 `Any`/裸 `dict` 注解——并对
观测契约维持磁盘 Schema 禁令。

## 否决方案

- 保留 `memory_observer`/`context_observer` 并继续新增按功能的 dict 回调；
- 为灵活性发出 `dict[str, Any]` payload；
- 维护导出的 JSON Schema 文件作为第二套契约事实源；
- 把 Brain 观测路由进 Infrastructure 模型执行观测，把能力面证据混入认知边界；
- 让 sink 抛异常，使 Brain 对采集器失败作出反应。
