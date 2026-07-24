# ElfieNest Godot 项目参考

## 项目契约

- 项目目录：`godot_project/`
- 项目文件：`godot_project/project.godot`
- 要求版本：Godot 4.7，GL Compatibility
- 主场景：`res://main.tscn`
- 最终巢穴场景：`res://rooms/nest.tscn`
- 场景资源契约：`res://scripts/test/test_scene_resource_contract.gd`
- Godot 生成缓存：`godot_project/.godot/`，已被 Git 忽略

主场景包含 `Nest` 和空的 `Characters` 容器。仅查看最终渲染时直接运行主场景，不需要同时启动编辑器、独立游戏进程和截图进程。

## 安全诊断顺序

1. 运行 `godot_guard.py doctor`，核对可执行文件和项目版本。
2. 运行 `godot_guard.py status`，确认没有已有 Godot 实例。
3. 使用 `godot_guard.py validate` 做资源契约检查。
4. 只选择 `editor` 或 `run` 之一启动。
5. 在同一个窗口完成日志观察和渲染检查。
6. 退出后检查 `git status` 和 `git diff`。

## 常见问题

### `.godot` 缓存含旧资源路径

先在工作区干净且没有 Godot 进程时确认缓存问题。`godot_project/.godot/` 是可再生目录，但删除或重建前必须说明影响并取得用户同意。不要通过连续启动多个实例竞争重建缓存。

### Godot 自动升级项目版本

Godot 主次版本与 `project.godot` 声明不一致时，可能改写 `config/features`，并给 `*.import` 增加新字段。默认拒绝版本不匹配的可编辑启动。若用户同意测试其他版本，操作后展示差异，不要擅自提交升级。

### 需要截图验收

优先截取现有 Godot 游戏窗口。系统无法按窗口截图时，直接说明限制并让用户查看当前窗口；不要默认再开一个 Godot 实例。只有用户明确要求生成 Viewport 图片、且当前没有 Godot 进程时，才能运行一次会自动退出的捕获流程。

### 需要关闭进程

先显示 PID、命令行和项目路径，只关闭能够确认由当前任务创建的 PID。禁止使用 `pkill Godot`、`killall Godot` 等批量命令。
