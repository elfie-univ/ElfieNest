# Desktop

Electron Desktop 是已认证的 Observer 与公开 lifecycle client，不是 Runtime
supervisor，也不是产品业务层。它的源码位于 `app/interfaces/desktop/`；原先的顶层
`desktop/` 目录不是当前模块。

## UI 角色、权威角色与 lease

普通 UI 角色取得 Electron 单实例锁，通过公开 CLI lifecycle client 挂接健康 Runtime
或启动一个 Runtime，随后打开同源 Core 登录页。产品路由访问控制与认证后的默认
`/chat` 或 `/manage` 落点由 Core 决定，不由 Electron 决定。

UI 若只是挂接，只会得到 Runtime generation。若由它启动 Runtime，则会得到 owner
lease；显式退出应用时，只有该 lease 才能回传给 CLI 停止 Runtime。关闭 Observer 窗口
不会停止它没有创建的 Runtime。

Godot 权威宿主由 Runtime lifecycle 边界选择并拥有。`electron_authority` 是独立、
沙盒化的 Electron 角色，在隐藏窗口加载已导出的 Godot Web 权威；它有独立 instance
namespace，不是 UI 角色。Desktop UI 不包含 Gateway 协议实现或权威凭据。

## Observer 表面

Desktop 渲染与其他产品客户端相同、已认证且 capability 受限的语义 Observer 表面。
它可以请求 resync、聚焦已经授权的房间或 Elfie，也可以提交单独授权的高层 interaction
请求。它不能读取 transform、相机状态或原始 Runtime 帧。第一阶段明确为非视频：本模块
不承载相机流或 JPEG 帧传输。

## 产品相机观察

同源、仅 Owner 可访问的 `/monitor` 路由渲染完整产品观察表面；Owner 的精灵巢管理弹窗
复用同一个 `ObservationMonitor` 表面，而不是创建另一套相机客户端。其完整、版本化的
相机目录由 Godot 拥有：语义 view `id` 与 `label`、`active_id`、正数 `revision` 和
`presentation_paused`。目录绝不暴露相机坐标、transform 或房间几何。

React bridge 只接受来自当前同源 Godot iframe、且满足严格版本化消息格式的目录。它只能
发出 `overview`、`select`、`reset` 与 `set_local_presentation_paused`；`select` 只能使用
当前目录中已有的 ID。它不能计算或发送相机位置、transform，也不能接触原始 Runtime 帧、
权威凭据或模拟控制。local presentation pause 只冻结 Observer 的本地输入/呈现状态；它
永远不会暂停 Runtime、Gateway、Core 或后端模拟。

## 产物契约与源码检查

Desktop 组件在 Runtime 产物清单中的名字是 `desktop-observer`。它恰好适用于
`darwin-arm64`、`darwin-x64`、`win32-x64` 与 `linux-x64`；每个 target 也要求
`godot-web`，只有 Linux 额外需要 `linux-dedicated`。契约验证 target 适用范围、模式、
入口和文件哈希。它描述必需产物形状，不表示存在安装包。

源码检查使用本模块锁定的 Node 工具链：

```bash
cd app/interfaces/desktop
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 test
```

编译后的 Desktop interface 输出属于 `build/components/desktop-interface/`。不要把生成的
JavaScript、Runtime 产物、模型或用户数据写回 `app/interfaces/desktop/`。
