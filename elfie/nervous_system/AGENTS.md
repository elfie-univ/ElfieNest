# Elfie NervousSystem 执行规则

本目录负责身体事件规范化、过滤、反射、感知投递，以及把已经校验的身体意图转换给
当前 `BodyPort`。

- NervousSystem 只处理 Elfie 身体与 Brain 之间的语义；不得拥有设备发现、注册策略、
  Godot 协议、几何、导航、进程或产品工作流。
- 身体事件和命令必须使用 `elfie/body/` 的标准模型并保留 `BodyId`；不得添加传输专用
  分支作为长期接口。
- 普通感知与动作只接受当前选中身体 generation；旧身体和非选中候选只能产生诊断
  事实，不得更新当前定位或取得动作 authority。
- 身体感知与数字通信感知保持不同语义流，不得为了复用而合并为无类型通用消息总线。
- NervousSystem 可保留连接两个 Elfie 子模块的内部 Adapter，但不得以此引入外部技术
  Adapter 或反向导入 App/Infrastructure。
