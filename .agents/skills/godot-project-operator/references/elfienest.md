# ElfieNest Godot 项目参考

## 项目契约

- 项目目录：`godot_project/`
- 项目文件：`godot_project/project.godot`
- 要求版本：Godot 4.7，GL Compatibility
- 主场景：`res://main.tscn`
- 最终巢穴场景：`res://rooms/nest.tscn`
- 场景资源契约：`res://scripts/test/test_scene_resource_contract.gd`
- Godot 生成缓存：`godot_project/.godot/`，已被 Git 忽略

主场景包含 `Nest` 和空的 `Characters` 容器。Godot 专项门禁只执行单次同步 headless 验证，不启动编辑器、独立游戏进程或截图进程。

## 安全诊断顺序

1. 运行 `godot_guard.py doctor`，核对可执行文件和项目版本。
2. 运行 `godot_guard.py status`，确认没有已有 Godot 实例。
3. 使用 `godot_guard.py validate` 做资源契约检查。
4. 只在无 Godot 进程时运行一次 `validate`。
5. 读取统一入口输出，确认进程已退出且没有崩溃或超时。
6. 结束后检查 `git status` 和 `git diff`。

## 常见问题

### `.godot` 缓存含旧资源路径

先在工作区干净且没有 Godot 进程时确认缓存问题。`godot_project/.godot/` 是可再生目录，但删除或重建前必须说明影响并取得用户同意。不要通过连续启动多个实例竞争重建缓存。

### Godot 自动升级项目版本

Godot 主次版本与 `project.godot` 声明不一致时，可能改写 `config/features`，并给 `*.import` 增加新字段。默认拒绝版本不匹配的可编辑启动。若用户同意测试其他版本，操作后展示差异，不要擅自提交升级。

### 需要视觉验收

视觉验收不属于 Godot 专项门禁。不要为了截图启动编辑器或第二个 Godot 实例；使用已经存在的用户窗口或独立的浏览器/UI 验收流程。

### 需要关闭进程

先显示 PID、命令行和项目路径，只关闭能够确认由当前任务创建的 PID。禁止使用 `pkill Godot`、`killall Godot` 等批量命令。
