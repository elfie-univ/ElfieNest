# ADR-0030：情绪状态仅在进程内存续并回归基线

**状态：** 已接受
**日期：** 2026-08-30

## 背景

情绪是短时、类似生理反应的运行状态。把当前存量、Frame 临时效果、重试账本或抑制指导
跨进程持久化，会保留已经过时的反应，并与 Event Workspace 的职责重复。人格、
Selfhood 和 Memory 已经拥有决定新一轮情绪起点的长期事实。

## 决策

Emotion 在同一只 Elfie 的运行进程内跨 Turn 连续存在。六个通道分别叠加、衰减，并向
人格决定的基线回归。进入睡眠或进程重启时，六通道回到基线，临时指导全部清空。

首版六个存量是 happiness、sadness、anger、fear、surprise 和 disgust。稀疏评价只给
确实受影响的通道提供正负语义强度；确定性 Owner 负责计算饱和增长、直接消耗存量和指数
回归。他人的情绪只是观察证据，不是 Elfie 的情绪；按关系加权的共情与直接自我相关评价
保持分离。

Emotion 不写入 Brain Journal，也不建立专用数据库。Coordinator 持有一个按 Frame
限定的内存事务，使快速评价在进程内重放时只应用一次，并让一次已校验的慢评价原子替换
快速结果。Event Workspace 继续拥有输入去重和持久 Pending Frame 恢复。

模型接收的是快速反应前的稳定 Emotion 投影和宿主可信候选 Scope，不是临时快速存量；
结构化慢评价必须从同一个快速反应前 Anchor 重新计算。具体动态和当前质量差距分别以
[Emotion 设计](../designs/elfie-emotion-system)和
[一致性台账](../conformance/elfie-emotion)为准。

音频/图像情绪检测暂缓。保留已有类型化媒体传输，但不保留无调用 Detector 占位代码；
未来 Detector 必须通过同一评价边界输出观察证据。

Memory 可以保存已经完成的经历及其历史情绪色彩；这不是当前 Emotion 状态的第二份副本。

## 后果

- 重启后的 Emotion 从人格基线开始。
- 已持久化但尚未完成的事件在重启后重新评价一次。
- 删除实时情绪 Checkpoint、事件账本和持久抑制记录。
- 旧的固定存量互动矩阵以及平行 VAD/Episode 状态不属于首版 authority。
- 语义 Effect 效果继续接受独立评测；确定性状态转移测试通过不能代替效果达标。
- Selfhood、Memory、Activity、回执及其他长期状态保持原有重启语义。
