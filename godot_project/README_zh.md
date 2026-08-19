# ElfieNest Godot 源项目

> 中文版：本文件 · [English](README.md)

`godot_project/` 是独立、可直接由 Godot Editor 打开的 Godot 源工程，也是
ElfieNest 3D 世界的唯一源码来源，负责房屋、几何、坐标、移动、碰撞、角色和
渲染。它不是 Python 包，也不是产品运行时直接读取的目录；Python Core 只通过
选中的已导出 Godot Runtime 及其协议交换巢内事件与状态，且不得复制这里的场景布局
或空间事实。

## 当前项目

- 项目文件：`project.godot`
- 引擎兼容版本源：`project.godot` 中 `config/features` 的第一项
- 主场景：`main.tscn`
- 渲染方式：GL Compatibility
- Web 导出预设：`export_presets.cfg` 中的 `Web`

主要源码分布：

```text
godot_project/
├── main.tscn、main.gd     # 项目入口
├── runtime/               # 世界配置、角色同步与语义动作生命周期
├── rooms/                 # Nest、房间、布局和家具资源
├── characters/            # Elfie 角色、模型、动画与外观制作资料
├── ui/                    # 观察界面
└── scripts/               # Godot 内部测试与资源制作工具
```

角色制作资料从 [`characters/README.md`](characters/README.md) 进入；房间资源
约定从 [`rooms/assets/README.md`](rooms/assets/README.md) 进入。

## 编辑安全

打开、运行、调试、截图或关闭 Godot 前，必须先遵守公开
[`AGENTS.md`](../AGENTS.md) 中的 Godot 操作门。本地编码代理如果还有可用的安全
操作技能，再按 `AGENTS.md` 的条件路由执行：

1. 检查已有 Godot 进程，避免重复实例；
2. 核对本机 Godot 与 `project.godot` 声明的版本；
3. 版本不匹配时，不得未经确认打开可编辑项目；
4. 操作前后检查 Git 状态，不保留 `.godot/`、导入缓存或无关 `.import` 噪声。

不要把 `godot_project/` 当作普通脚本目录直接批量格式化，也不要把编辑器生成物当作
源码提交。

## Web Runtime

终端用户的 Observer 客户端使用导出后的 Godot Web Runtime，不需要安装 Godot Editor。
第一阶段是语义、非视频的，不暴露相机或 JPEG 帧传输。正式产物只能进入：

```text
build/components/godot-web/
```

在仓库根目录构建或检查：

```bash
GODOT_BIN=/path/to/godot ./developer.sh build-godot-web
./developer.sh build-godot-web --check
```

构建器会核对引擎版本、检查必需产物、生成哈希清单，并在成功后替换正式输出。
Runtime 产物契约可以引用同一份产物；不要在 `godot_project/`、
`app/interfaces/desktop/` 或普通用户 Web 源码中维护副本。

Web 导出的环境准备、目录和验收细节只在
[`WEB_EXPORT.md`](WEB_EXPORT.md) 维护，避免出现多份互相漂移的流程。

## Linux Dedicated Runtime

无显示的权威 Runtime 是单独的 Linux x64 导出，只能写入：

```text
build/components/godot-linux-dedicated/
```

从仓库根目录使用与 `project.godot` 声明匹配、且已安装 Linux x64 Export Template
的 Godot 构建或检查：

```bash
GODOT_BIN=/path/to/godot ./developer.sh build-godot-dedicated
./developer.sh build-godot-dedicated --check
```

Dedicated 预设强制启用 Godot 的 `dedicated_server` feature 与 headless 运行。
它只能作为权威宿主：不会创建显示窗口，也不会上传 JPEG 摄像头帧。

## 与 Python 的运行边界

唯一的权威 Runtime 通过 Gateway 语义协议接收 `configure_world`、`sync_actors`、
`execute_intent` 和 `cancel_intent`。Runtime 生命周期从图形化 Web、图形化 Electron
权威角色或无显示 Linux Dedicated 中选择一个权威宿主。Godot 负责：

- 根据床位数重建固定房间，并发布稳定的 zone/anchor 语义目录；
- 生成导航网格、逐物理帧寻路、碰撞与避障；
- 加载狐狸/狗/猫角色场景，播放移动、姿态和表情；
- 计算触觉接触和说话听众，并回传带 revision/generation 的类型化事件。

Python 不发送逐帧坐标，也不在 `nest/` 复制家具占用或碰撞几何。一个
`execute_intent(intent="move_to_anchor")` 可以在 Godot 中持续多个物理帧；遇到阻塞、取消、超时或最终完成时
再回传生命周期事件，让精灵大脑依据真实结果继续决策。
