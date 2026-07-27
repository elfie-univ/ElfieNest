# 代码规范与约束

这页是所有贡献者和编码代理的共同入口。规则的目标是让边界、类型和验证方式
直接体现在代码里，而不是依赖某个人的记忆。

## 先遵守目录边界

- `elfie/` 只实现单个完整 Elfie；不放账户、Web、Godot 场景或桌面生命周期。
- `nest/` 只保存巢内状态和环境；真实 Elfie 与 Nest 的组合只能进入
  `app/orchestration/`。
- `ai_runtime/` 管模型、Provider、工具、粮食和安全运行时。
- `godot_project/` 是房间、几何、坐标、碰撞与渲染的唯一源码来源。
- `app/orchestration/lifecycle/` 负责 Runtime 监督与权威生命周期；
  `app/interfaces/desktop/` 负责 Electron Observer interface 和公开 lifecycle client。

新增目录或跨边界依赖时，必须同时更新根 README、架构文档和
`test/architecture/` 契约测试。

## Python 约定

- 使用锁定的 CPython `3.9.25`、`uv.lock`、Ruff 和 MyPy。
- 类型优先：公共函数、模型和事件必须有明确类型；不要用无约束的 `Any` 掩盖边界。
- 数据结构以代码中的 Pydantic 模型为唯一事实来源；不为内部模型维护重复的 JSON
  Schema 文档或导出文件。
- 测试目录镜像源码目录，使用绝对导入；禁止把临时测试放到 `test/` 根目录。
- 小步修改，先运行离改动最近的测试，再运行架构契约和质量门。

## 文档约定

- 公开设计文档默认使用英文，并同步简体中文版本；两侧都描述最终方案、代码证据和验证方式。
- 中间讨论、未实现方案、私有世界观和实验记录留在公开文档之外，不进入 VitePress 侧栏。
- README 说明“是什么、怎么开始、去哪里深入”；不要把过程日志当作产品文档。

## 交付前检查

```bash
uv run --no-sync pytest test/architecture/
uv run --no-sync python scripts/check_quality_baseline.py
cd docs && npx --yes pnpm@10.12.1 build
```

提交前还必须通过 pre-commit 和密钥扫描；不要用 `--no-verify` 绕过检查。
