# 运行时与数据

## 进程关系

```text
Electron Desktop
  ├─ Python Core
  ├─ Ollama 或其他 Provider
  └─ Godot Web Runtime
```

Desktop 负责窗口、资源和进程监督；Python Core 负责产品、Elfie、Nest 与 Runtime；
Godot 负责空间事实和渲染；模型服务负责推理能力。

## 数据目录

| 类型 | 位置 | 是否提交 |
| --- | --- | --- |
| 用户配置、数据库、精灵档案、本地密钥 | `${ELFIE_HOME:-~/.elfienest}` | 否 |
| 可再生中间产物 | `build/` | 否 |
| 最终发行物 | `dist/` | 否 |
| 公开文档源 | `docs/` | 是 |
| 历史和私有过程材料 | `.omo/`、`.agents/knowledge/` | 否 |

## 生产目录契约

一台电脑只有一个生产 Nest 根 `${ELFIE_HOME:-~/.elfienest}`。根目录保存 Nest 级
别事实：`config.yaml`、`.env`、`foods.yaml`、`nest.db`、备份、运行态及日志。
`nest.db` 只保存账号、权限、精灵登记/归属、Nest 世界与运行状态；它不再接收新的
聊天消息。

每只精灵都以不可变的 `elfie_id` 作为工作区名。显示名称可改，但绝不能改动目录：

```text
${ELFIE_HOME:-~/.elfienest}/
├── nest.db                         # Nest、账号、归属和世界状态
├── config.yaml / .env / foods.yaml # 本机生产配置与密钥引用
└── elfies/
    └── <elfie_id>/                 # 稳定 ID，不使用可变名称
        ├── profile.yaml 等档案、记忆和工作内容
        └── conversations/
            └── history.sqlite      # 该精灵的所有本机渠道聊天
```

`history.sqlite` 记录会话、渠道、发送方、用户关系、文本、元数据和附件引用。不会建立
用户视角的本机聊天副本，也不会把附件二进制塞进数据库。网页、桌面、微信或飞书等
渠道都按所属精灵写入这一个工作区。

## 开发边界

Developer Tools 默认使用独立根 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，其下的
`elfie_lab/`、`nest_lab/`、`runtime_lab/` 不得回退读取生产根。测试应同时设置临时
`ELFIE_HOME` 与 `ELFIE_DEV_HOME`。

`nest.db.chat_messages` 是未发布阶段遗留的废弃表。数据库升级会直接删除它；不提供
兼容读取、复制或迁移工具。新聊天只能位于对应精灵工作区。

## 内部契约

Pydantic 模型是内部数据结构的唯一事实源。代码需要时可以运行时调用
`model_json_schema()`；仓库不维护第二份 JSON Schema 文件。
