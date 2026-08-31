# ADR-0031：Selfhood 拥有四段固定模型头中的两个个体段

**状态：** 已接受
**日期：** 2026-08-30
**范围：** Selfhood authority、Genesis 初始化与在线 Elfie `ReasoningRun`
上下文组装

## 背景

既有 Brain 架构已经把 Selfhood 与 Memory、Profile 分开，但实现与契约仍把 Profile 写成
Selfhood 的运行时锚点。普通思考会投影当前 Profile 与 Canon；Selfhood 保存一份混杂的
扁平记录；Memory 又维护一套核心自我叙事；通用 continuity checkpoint 还能恢复第二份
Selfhood。

Reasoning 同时在代码里临时拼装身份、行为、响应和知识边界提示。大五人格原始数值直接
交给模型，而全应用故事框架与运行约束没有唯一受审来源。因此无法明确回答：哪个事实是
authority、哪些内容稳定、每个在线思考请求必须保存哪一个准确前缀。

## 决策

接受 [Selfhood 与固定模型头部设计](../designs/elfie-selfhood-and-fixed-model-header.md)，
并把 Elfie 契约升级到 2.2、Brain 契约升级到 1.3。

1. 在线 Elfie `ReasoningRun` 内的每个模型请求，必须以严格有序的四段 system 头部开始：
   `APPLICATION_FRAME`、`IDENTITY_CORE`、`ADAPTIVE_SELF`、
   `OPERATING_CONTRACT`。
2. 一份由人编写、required、bundled-only 的 `ReasoningConstitution` 拥有第一、第四段。
   Infrastructure 校验，Bootstrap 注入；Genesis、用户、Provider 和模型均不能生成或覆盖。
3. 一份原子 Selfhood 状态拥有中间两段。`identity_core` 保存创建后冻结的最低限度个体
   身份；`adaptive_self` 保存缓慢人格、个人价值、互动、应对和表达倾向。Selfhood 用
   确定性投影生成两段自然语言。
4. Genesis 读取已接受的领养输入与创建时 Canon，并列物化 Profile、Selfhood 和 Genesis
   Memory。Profile 仍是外层客观档案；普通 Brain 运行期既不读取 Profile，也不读取
   Canon，更不会按两者同步 Selfhood。既有 Elfie 不保存 Canon 版本绑定。
5. 第一阶段没有 adaptive 更新线路。后续设计最多允许 Memory 整理生成强类型 proposal，
   请求有界修改 `adaptive_self`；Selfhood 仍负责校验与持久提交，`identity_core` 永久不可变。
6. 每只 Elfie 的 Selfhood 文档是第一阶段唯一持久 authority。通用 Brain continuity
   checkpoint 不包含 Selfhood，模型投影不持久化；状态缺失或无效时必须在模型调用前
   失败，不得从 Profile、Canon、Memory 或通用 persona fallback。
7. 动态运行协议与当前状态放在固定头之后。检索 Memory、Activity、观察、对话历史与
   当前消息都是上下文数据。宿主能力、Scope、提交与回执校验仍是真正的执行 authority。

固定头覆盖同一在线 Run 的初始、Tool 续跑和修复调用，并在该 Run 内保持逐字节稳定。
Genesis、Memory 整理、Provider 探测、评价 Judge 与无身份后台 Worker 不使用此头部。
Model/Provider Adapter 只能传输请求，不能新增 system 指令或改变 Brain 拥有的消息顺序/
内容；Skill/Tool 指令进入固定头之后、由 Brain 拥有的 `TURN_PROTOCOL`。

## 后果

- 同一只 Elfie 不再让 Profile、当前 Canon、Selfhood 与 Memory 竞争运行时身份 authority。
- 全应用提示语义可以统一受审并在所有机器上完全一致地发布，不产生每只 Elfie 的副本。
- 内部数值人格仍可供强类型 Brain 消费者使用；模型拿到的是有界自然语言投影，而不是原始
  数字或字典。
- 动态 Emotion、Energy、Orientation、能力与响应 Schema 保持在四段之外，不变成 Selfhood。
- 自动成长、成长算法和既有 workspace 迁移保持关闭，直到独立设计提供证据与持久化规则。
- 第一阶段源码已实现上述 authority、固定头部和 fail-closed 边界；[Selfhood 一致性台账](../conformance/elfie-selfhood.md)
  继续保留真实模型行为矩阵与既有 workspace 迁移两项开放项。不能用结构性测试把这些差距
  掩盖掉。

## 被否决的方案

明确否决：新增独立 `IdentityKernel`；Reasoning 从 Profile/Canon/Memory 重建身份；把最终
Prompt 段落保存成状态；用 Memory 核心叙事充当 Selfhood；把大五人格原始数值当行为协议；
把 Turn 动态 Schema 塞进固定 Operating Contract；同时用 YAML 和通用 checkpoint 保存
Selfhood；成长算法尚未设计时开放宽泛更新接口；以及把提示词当作安全执行边界。
