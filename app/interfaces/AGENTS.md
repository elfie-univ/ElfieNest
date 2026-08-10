# Interface 层执行规则

本目录包含 HTTP、WebSocket、Web、CLI 和 Desktop 等协议入口。

- 只负责认证入口、协议校验、严格 DTO、Feature/Orchestration 调用、错误映射和响应
  序列化；不得承载业务规则、SQL、路径解析或具体 Adapter 构造。
- 依赖公开 Feature 用例或 Orchestration Facade，不导入其内部模块，也不导入
  Infrastructure 或 Bootstrap。
- 原始请求、WebSocket 帧、前端松散对象和 SDK 类型必须在边界校验并映射；不能跨入
  产品层。
- 页面和客户端不是业务事实源。Web、Desktop、CLI、Setup 和未来移动端复用同一产品
  用例，只获得不同权限投影。
- 子目录可细化各自协议，但不能新建重复的业务实现或 Runtime authority。
