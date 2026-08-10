# Bootstrap 组合根规则

本目录是 App 唯一生产组合根，只负责创建、注入、对象生命周期和启动/收束装配。

- 可以导入 Feature/Orchestration 契约与具体 Infrastructure Adapter，但产品代码不得
  反向导入 Bootstrap。
- 在这里集中选择实现、解析进程级依赖并构建应用容器；Interface 只接收已经装配好的
  Service/Facade。
- Runtime 组件启动、停止和重启的决策与流程只属于
  `app/orchestration/lifecycle`；本目录只构造并调用其公开边界。测试和隔离开发工具
  可以构造 Fake 或沙箱 Container，但不能成为第二个生产组合根。
- 不写授权、业务条件、SQL、协议 DTO 映射、模型推荐算法或第二套配置事实。
- 明确 process、request/use-case、connection、job 四类生命周期；不得把连接、事务或
  Principal 缓存为进程单例。
- 禁止 Service Locator 和运行时全局查找；依赖必须通过构造参数或明确工厂传递。
