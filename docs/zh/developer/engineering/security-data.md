# 安全与数据边界

ElfieNest 把“精灵的长期生活数据”和“源码、构建物、公开文档”分开管理。任何新
功能都要先说明数据写到哪里、由谁拥有、如何清理。

## 产品数据根

- 安装版 App、托盘和全局 CLI 只使用 `${ELFIE_HOME:-~/.elfienest}`。配置
  `ELFIE_HOME` 后，默认根不读不写；禁止 remembered 第三根或激活命令。
- 源码与 worktree CLI 忽略调用方 `ELFIE_HOME`。只有 `start`、`serve`、`restart`、
  `stop` 接受 `--data-home`；其余命令使用纯内存会话上下文、对当前命令可用的
  `<当前worktree>/.elfienest.local` 或经验证候选选择。
- 产品 PID/锁、`runtime/runtime.json`、日志和数据库只跟随唯一解析根。源码 CLI history
  及候选目录位于仅所有者可访问的可选子目录
  `<source-root>/.elfienest.local/runtime/cli/`；产品数据完整性和 Runtime 身份判断忽略
  该子目录。候选目录可以列出数据根，但不能保存活动根、PID、endpoint、凭据或进程控制权。
- 不存在持久化 remembered-root authority 或激活 fallback。旧的
  `selected-data-home` 文件保持惰性，绝不作为当前数据根读取。
- 测试、实验台和文档验收必须使用独立的 `ELFIE_HOME` 或临时目录。
- `build/` 只存中间产物，`dist/` 只存最终发行物；两者都不属于源码文档。

生产根内部按 Nest 与精灵两层归属。`nest.db` 只保存最终 8 张 Nest 级表；每只精灵的
档案、记忆、工作内容与聊天位于
`elfies/<elfie_id>/`。`elfie_id` 是不可变目录 ID，名称变更不能移动数据。
新聊天只能写入 `elfies/<elfie_id>/conversations/history.sqlite`，不创建用户聊天
目录，也不在 `nest.db.chat_messages` 写入副本。
新建数据目录使用仅所有者可访问的 `0700`；数据库、档案、配置、密钥和生命周期
回执文件使用 `0600`。`db backup` 把三类数据库一起写入数据根旁的备份树；
`db reset` 删除三类数据库，但保留非数据库文件。

Developer Tools 使用独立 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，并继续分别使用
`elfie_lab/`、`nest_lab/` 子目录；不能默认读取或写入产品数据根。
应用在写入前拒绝旧数据根；0.x 首版唯一支持的处理方式是先备份，再用空根重建。

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
