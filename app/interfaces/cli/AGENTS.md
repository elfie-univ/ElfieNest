# CLI Interface 规则

CLI/TUI 是协议入口，不是第二套产品实现。

- 解析参数、校验输入、调用公开 Feature/Orchestration Facade 并格式化输出；不得直接
  SQL、创建 Repository、解析生产数据根或复制业务规则。
- 命令与 HTTP/桌面复用同一用例和错误语义；脚本友好输出使用稳定结构，终端文案不能
  成为机器契约。
- 生命周期命令只调用公开 lifecycle client，不直接创建 Supervisor/Gateway/Godot。
- 安装版全局 `elfienest` 是生产 Controller 的控制客户端：`start` 不打开 Viewer，也不
  直接创建第二套 Server。源码 `./elfienest.sh` 才是支持隔离数据根和前台 `serve` 的
  开发入口。
- Secret 不进入命令历史、普通 stdout 或日志；交互式输入按敏感信息处理。
- 新增命令必须有聚焦解析/调用测试，不能借 CLI 入口绕开授权。
