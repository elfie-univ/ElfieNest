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

## 内部契约

Pydantic 模型是内部数据结构的唯一事实源。代码需要时可以运行时调用
`model_json_schema()`；仓库不维护第二份 JSON Schema 文件。
