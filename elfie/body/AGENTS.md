# Elfie Body 执行规则

本目录拥有身体领域语义：`BodyId`、能力、解剖、命令、传感事件、回执、Registry 和
Binding。`BodyPort` 是多具可替换身体共同实现的出站边界。

- 一只 Elfie 可以注册多具身体；每个实例有稳定身份、能力修订和独立生命周期。当前可
  只绑定一个主命令身体，但不得把“已连接”隐式当作绑定策略。
- 命令、事件和回执必须保留身体身份与类型化语义；禁止把 Godot 帧、设备包、Socket、
  蓝牙/LAN 协议或凭据加入公共模型。
- Godot、实体设备、网络传输、进程控制及产品 Headless 托管最终属于 Infrastructure
  Adapter。现有 `native/`、`external/` 是 `ELF-006` 迁移债务；`headless/` 必须区分
  为确定性无 I/O 的领域参考/测试 Fake，或随产品托管实现一起迁出，不得按目录名猜测
  所有权，也不得复制兼容路径。
- Registry/Binding 只管理 Elfie 内身体语义；设备发现、授权、关联和跨 authority 工作流
  属于 App Feature/Orchestration。
- Registry 只接收 App 已经发现、授权和关联的限定作用域 Body View；连接或健康状态不
  能自动授予、关联或绑定身体，多身体事件也不存在隐式全局顺序。
- Body Channel 只承载 Actor 作用域命令、感知、本体感觉和回执；房屋几何、坐标、
  碰撞/导航与全局互动事实必须经 Nest World Channel，`BodyPort` 不得绕过 Nest
  authority，即使两者复用同一个 Godot Gateway。
- 只有某具身体内部确有独立测试价值时才增加窄 Sensor/Actuator Protocol；不得复制一套
  面向调用方的身体 API。
