# ADR-0036：标准流程 Skill 与强类型可执行 Tool

- **状态：** accepted
- **日期：** 2026-09-03
- **范围：** Brain Reasoning、内置 Skill 资源和 Infrastructure Tool

## 背景

旧实现把可执行工具 key 的映射叫作“Skill”，并通过模型可见的文本标记请求执行。
这混淆了两种不同能力，也让模型协议依赖 Prompt 解析。

## 决策

Skill 和 Tool 使用两份独立契约：

- Skill 是一个官方内置目录，包含带 `name`、`description` frontmatter 的
  `SKILL.md` 和流程正文。Brain 先公开元数据，再在 deliberate 的
  `ReasoningRun` 内通过只读原生 `load_skill` 控制操作加载一份获批文档。
- Tool 是带稳定名称、描述、JSON 输入/输出 Schema、执行处理器和安全限制的
  强类型可执行能力。内置定义显式注册在 `infrastructure/tools/`；现有 `ToolPort`、
  配置、权限、作用域资源、观测和限制仍是执行 authority。
- 内置 Skill 源位于 `config/brain/skills/<name>/SKILL.md`，发布时 staging 到
  `resources/config/...`。本阶段禁用用户/第三方安装、Skill 脚本、修改和单只 Elfie
  持久 Skill 状态。
- DIRECT 永不向模型提供 Skill 或 Tool。DELIBERATE 可以提供所选 Provider 支持的
  强类型能力。不支持原生 Tool Calling 的 Provider 不接收 Tool，也没有文本标记 fallback。

## 后果

模型/Provider 边界传递原生 Tool call 和 Provider 原生 observation 消息。Tool 授权独立于
Skill 加载，因此加载流程文档不能扩大技术能力。现有网页搜索和限定工作区本地文件行为
继续沿用同一条生产 `ToolPort` 链路。

## 否决方案

- 把 Tool key 当作 Skill 定义；
- 继续把 `[SEARCH]`/`[READ_FILE]` 标记解析成兼容执行协议；
- 扫描任意目录或执行 Skill 脚本；
- 让不支持原生 Tool Calling 的 Provider 接收隐藏标记指令。
