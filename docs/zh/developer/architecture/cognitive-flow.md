# 认知信息流

> 本页说明当前可执行链路。所有权、Facade，以及 Food/模型/工具、Body、通信和持久化
> Port 以 [Elfie 内部架构契约](../contracts/elfie)为规范，并由永久架构测试执行。

Elfie 的输入和输出不是一段统一的聊天字符串，而是按身体、通信和内部执行分别路由
的类型化事件。

```text
Body → NervousSystem ───────┐
                            ├→ PerceptualWorkspace
Communication ─────────────┘
                                      ↓
                              BrainCoordinator
                                      ↓
                               BrainContext
                                      ↓
                               DecisionPlan
                         ┌────────────┼────────────┐
                         ↓            ↓            ↓
                       Body     Communication   Internal
                         └────── ExecutionReceipt ────┘
                                      ↓
                              PerceptualWorkspace
```

## 一次回合

1. `ElfieNestEngine` 推进时钟并泵送身体事件；
2. `NervousSystem` 与 `Communication` 向工作区写入独立事件；
3. `BrainCoordinator` 封存感知帧并提交异步认知回合；
4. `DecisionPlan` 由 `OutputRouter` 分发到具体输出端；
5. 执行结果生成 `ExecutionReceipt`，供下一次感知使用。

这条链路允许物理动作继续推进，不必等待模型完成；也让每一类输入、输出和回执都能
单独测试和重放。
