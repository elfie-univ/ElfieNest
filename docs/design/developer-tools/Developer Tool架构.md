# Developer Tool 架构

## 目标

普通用户只接触 ElfieNest Desktop 和完整服务；开发者调试工具使用独立入口、独立网址和独立数据目录，不进入普通用户导航。

## 统一入口

```text
./developer.sh
└── python -m devtools
    ├── elfie-lab    单精灵感知、记忆和决策链路
    ├── runtime-lab  Provider、模型和连接测试
    └── nest-lab     精灵巢房间、碰撞、运动和 Godot 通信模块
```

也可以直接运行 `./developer.sh nest-lab`。每个工具的默认数据目录都在 `~/.elfienest/developer/` 下：

```text
developer/
├── elfie_lab/
├── runtime_lab/
└── nest_lab/
```

`nest-lab` 默认使用 `127.0.0.1:8890`，不连接正式的 `ElfieNestEngine`、生产数据库、普通用户鉴权或普通用户前端资源。它是验证房间状态、碰撞、运动和 Godot WebSocket 协议的单独实验台。

`./developer.sh elfie-lab` 默认监听 `127.0.0.1:8877`，服务就绪后自动用系统默认浏览器打开该地址。它使用独立的 `elfie_lab/elfies`、`sessions`、`media` 和 `trash` 数据边界；可以读取公共 Runtime 粮食目录，但不复用普通用户鉴权、页面或生产精灵注册表。

Elfie Lab 的左侧只拥有一个 Godot Web iframe。相机操作和历史动作按钮都通过带 `request_id` 的 Lab 协议驱动该实例，右侧详情只保存状态和控制信息，不加载第二份角色资源。Godot Web 导出缺失时，精灵管理、文字/图片刺激、Debug 注入和历史详情仍须可用。

## 普通用户服务边界

普通用户入口是 `./elfienest.sh start` 或打包后的 ElfieNest Desktop。打包环境中，Python Core、Ollama 和 Godot Web Runtime 由 Electron 主进程统一监督：

```text
Ollama 后台服务
    ↓ 健康检查
Python Core（数据库、精灵大脑、房间状态）
    ↓ HTTP 就绪
隐藏 Electron BrowserWindow（Godot Web Runtime）
    ↓ runtime_ready / WebSocket
主管理窗口（Electron + Chromium）
```

停止时按反向顺序关闭。Python Core 不再自行查找或启动 Godot 编辑器/运行时，避免两个 supervisor 重复拉起同一个核心。源码仓库尚未构建 Desktop 时，`start` 会回退到 `scripts/serve.py` 作为开发调试路径；发布安装包必须携带三套运行时，不要求用户安装 Godot、Python、Node 或 Ollama。

## 构建职责

Godot 编辑器和 Web Export Templates 只属于开发者/构建机。`./developer.sh build-godot-web` 生成的 Web 资源随 Desktop 安装包发布，用户运行时只加载导出的 HTML/JS/WASM/PCK，不打开 Godot.app。
