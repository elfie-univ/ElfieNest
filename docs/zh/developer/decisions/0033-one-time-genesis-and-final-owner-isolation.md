# ADR-0033：Genesis 只编译一次，已提交 Elfie 只依赖最终所有者

**状态：** 已接受
**日期：** 2026-09-01
**范围：** 创建资料所有权、领养输入、Genesis 编译、Profile/Selfhood/Memory
物化与创建后的运行依赖

## 背景

ADR-0031 已经把 Profile 和当前 Canon 从普通 Brain 思考中移除，但创建边界仍没有写透。
当前代码和设计文字还容许几种互相冲突的解释：Profile 可以保存生成 Seed、用户选择、
能力引用和抵达事实；Selfhood 可以暴露 Profile/Canon 投影；Infrastructure 持久化
Adapter 又可以在写工作区时决定个人知识、人物关系和经历。部分文档还把完整创建
Manifest 与原始领养答案当成已经提交的 Elfie 日后重放所需的永久输入。

这些解释制造了多个竞争 authority，也让 Profile 究竟是外部档案还是世界模型容器、
Infrastructure 究竟是 Adapter 还是生命生成器、既有 Elfie 究竟从自己的终态恢复还是
按新世界资料重新生成，都变得不清楚。

ADR-0032 另行确立 Reasoning Context Workspace 与持久 Memory 的边界。本文建立在该普通
Reasoning 隔离已经成立的基础上，继续规定 ADR-0032 未覆盖的上游创建事务和提交后断源。

## 决策

把 Elfie 契约升级到 2.3、Brain 契约升级到 1.5、Application 契约升级到 1.11，
Configuration 契约升级到 1.4。

1. 创建资料只有一个向下方向：
   `CreatorWorldSkeleton -> ResidentKnowledgeBaseline -> published
   GenesisSourcePackage`。个体创建开始前，这条链已经完成人工确认与程序校验；它既不是
   普通运行依赖，也不是第二份个人知识库。
2. 已接受领养选择、生成出的 `LifeContext`、`PersonalGenesisPlan`、随机 Seed 和资料包
   绑定都只是创建事务数据。`elfie/genesis/` 拥有确定性的语义编译器和校验规则。模型
   最多渲染受限、非权威的语言，不能决定身份、知识、人物、关系、经历或 Memory 策略值。
3. 一份已校验创建 Bundle 并列物化最终所有者产物：外部 Profile、Brain Selfhood、
   Brain Memory，以及其他明确归属 owner 的启动 Seed。App `resident_admission` 只协调
   提交、恢复与补偿。Infrastructure 只通过使用方 Port 加载强类型源文档并持久化强类型
   输出，不能编译一段生命。
4. 创建成功提交后，必须切断对全部创建输入的运行依赖。普通启动和运行只恢复各最终 owner
   已提交的状态，不能从 Canon、资料包、问卷、`LifeContext`、计划或生成 Seed 重新加载、
   刷新或再生。原始答案和生成期记录在提交或终止失败后删除。未完成事务只能暂存崩溃恢复
   所需的有界候选/输出资料。Profile 之外可以保留最小技术提交回执用于幂等与审计，但其中
   不得包含问卷、世界知识、重放 Seed 或完整人生计划。
5. Profile 是冻结的外部客观档案，不是创建账本。语义白名单只有：稳定身份
   （`elfie_id`、最终名字、正式物种及适用时的固定性别）、稳定年龄/出生锚点、不可变个人
   出身地点标识与名称，以及最终虚拟外貌；技术 Schema revision 可以保留。Profile 不得
   包含世界知识和 Canon 引用、生成器/模型/策略版本、Seed、用户选择、资料包哈希、抵达/
   培训经历、关系、传记、人格、自我认知、能力、权限、预算、当前身体或运行状态。
6. Selfhood 拥有 Elfie 内部身份和人格；Memory 拥有这只 Elfie 实际知道的知识、人物与
   关系及全部经历，包括离开、培训、抵达和领养经历。Profile 与 Selfhood 只能在创建时
   作为经过共同校验的并列快照重复最低限度身份值；运行期谁也不能从另一方派生或同步。
7. 普通 Brain 只使用 Selfhood、Memory 与当前 Brain 状态。Profile 只服务获授权的外部
   档案/投影和聚合身份校验；Reasoning 看不到创建资料。发布新版资料包只影响未来创建。
   改变既有 Elfie 必须另行批准迁移或作为世界内真实学习事件发生，不能静默重新生成。

ADR-0006 继续作为生命系统所有权的历史决策，ADR-0031 继续负责 Selfhood 与固定模型头，
ADR-0032 继续负责 Reasoning Context Workspace 所有权。当这些较早文字把创建来源放入
Profile，或没有明确创建输入生命周期时，以本决策为准。

## 后果

- 派生只有一个方向，运行期不存在回到世界源资料的支路。
- Profile 可以安全对外展示，不暴露私人答案、生成内部信息、认知状态或世界百科。
- 备份和恢复保存 Elfie 已提交的终态，不要求保留旧资料包才能重新造出同一个人。
- Genesis 算法留在领域中，保持确定、可测试；存储和配置 Adapter 仍是可替换技术边缘。
- 当前源码尚未完全符合。Elfie、Selfhood 和 Configuration 一致性台账会继续开放，精确
  记录 Profile、编译器位置、重复资料源和输入清理缺口；本次治理决策不冒充产品迁移已完成。

## 被否决的方案

明确否决：把 Profile 当成所有不可变字段的杂物袋；永久保存问卷或 Seed 用于重新生成；
让 Canon 成为 Brain 运行输入；内置世界资料升级后刷新既有 Elfie；把语义生成放进持久化
Adapter；让模型自由编造结构化人生计划；把抵达历史保存为客观 Profile；以及在运行期同步
Profile 与 Selfhood。
