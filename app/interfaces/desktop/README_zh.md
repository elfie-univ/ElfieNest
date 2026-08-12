# ElfieNest Desktop interface

> 中文版：本文件 · [English](README.md)

`app/interfaces/desktop/` 是 Electron Observer interface，负责可见窗口、UI 单实例
行为、平台集成和公开 lifecycle client。它不拥有 Runtime、Nest 业务状态、账户、聊天、
Godot Gateway 协议或权威凭据。

## Lifecycle client

UI 角色创建唯一的 owner ID，并调用公开的 `elfienest` lifecycle 命令。它会挂接已经
健康的 Runtime，或者启动一个 Runtime 并取得对应 owner lease。返回的 generation 足以
观察；显式退出应用时，只有匹配的 lease 才能停止 Runtime。关闭窗口没有生命周期副作用。

Core 负责登录和路由选择：Desktop 打开同源登录页，认证后由 Core 选择 `/chat` 或
`/manage`。

## 独立权威角色

UI 角色不是 Godot 权威。`app/bootstrap/desktop_host/` 是 Electron 组合入口，负责
分发可见 Desktop interface 或 Infrastructure 拥有的 `godot-authority` 入口。权威使用
自己的 instance namespace，在隐藏且沙盒化的窗口中加载已导出的 Godot Web Runtime；
Desktop 源码与自身 package metadata 都不导入或打包该权威。

Observer 接收受限范围的语义投影，只能发送已授权的高层 intent。它从不接收场景几何、
transform、原始 Gateway 帧、相机状态或权威凭据。第一阶段没有相机/视频或 JPEG 帧传输。

## 产物与构建边界

Runtime 产物契约要求 `desktop-observer` 恰好适用于 `darwin-arm64`、`darwin-x64`、
`win32-x64` 与 `linux-x64`。每个 target 也要求 `godot-web`；只有 Linux 要求无显示的
`linux-dedicated` 权威组件。该契约验证产物元数据和哈希，不表示安装包已经构建。

源码检查需要 Node.js 20 和仓库锁定的 pnpm 10.12.1：

```bash
cd app/interfaces/desktop
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
npx --yes pnpm@10.12.1 test
```

生成的 interface 输出属于 `build/components/desktop-interface/`。原生包组合配置由
`app/bootstrap/desktop_host/electron-builder.yml` 拥有。不要把生成的
JavaScript、Runtime 产物、模型或用户数据写回本源码目录。
