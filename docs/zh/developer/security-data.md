# 安全与数据边界

ElfieNest 把“精灵的长期生活数据”和“源码、构建物、公开文档”分开管理。任何新
功能都要先说明数据写到哪里、由谁拥有、如何清理。

## 产品数据根

- 正式安装运行按 `--data-home PATH`、`ELFIE_HOME`、`~/.elfienest` 的顺序解析
  数据根。
- 源码与 worktree 运行按 `--data-home PATH`、`ELFIE_HOME`、
  `<当前worktree>/.elfienest.local` 的顺序解析数据根。
- `serve` 和 `start` 支持 `--data-home PATH`。生命周期命令会记住该选择，让
  `status`、`stop`、`restart` 使用同一数据根；PID、锁、`runtime.json`、日志、
  CLI history 和 `nest.db` 都跟随该根。
- 测试、实验台和文档验收必须使用独立的 `ELFIE_HOME` 或临时目录。
- `build/` 只存中间产物，`dist/` 只存最终发行物；两者都不属于源码文档。

生产根内部按 Nest 与精灵两层归属。`nest.db` 只保存最终 8 张 Nest 级表；每只精灵的
档案、记忆、工作内容与聊天位于
`elfies/<elfie_id>/`。`elfie_id` 是不可变目录 ID，名称变更不能移动数据。
新聊天只能写入 `elfies/<elfie_id>/conversations/history.sqlite`，不创建用户聊天
目录，也不在 `nest.db.chat_messages` 写入副本。

Developer Tools 使用独立 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，并继续分别使用
`elfie_lab/`、`nest_lab/`、`runtime_lab/` 子目录；不能默认读取或写入产品数据根。
应用在写入前拒绝旧数据根；MVP 唯一支持的处理方式是先备份，再用空根重建。

## 密钥与外部服务

- API Key、Token、密码只从环境变量或被 Git 忽略的用户配置读取。
- 示例配置只能使用 `${API_KEY}` 或 `<your-api-key-here>` 占位符。
- 不要在 README、设计文档、测试 fixture 或截图中写入真实凭据。

## 公开文档边界

公开站点只发布已审阅的产品介绍、使用方法和最终开发说明。中间设计稿、实验证据、
未上线能力和私有世界观留在公开文档之外，不得被 VitePress 构建引用。

## 变更检查清单

1. 确认新增文件不在私有材料或构建目录中。
2. 搜索密钥模式和本机绝对路径。
3. 检查文档构建产物没有出现 denylist 词条。
4. 用最小权限运行外部服务，不把调试端口暴露到普通用户导航。
