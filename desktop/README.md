# ElfieNest Desktop

`desktop/` 是跨平台 Electron 宿主，只负责桌面生命周期、窗口、平台资源发现和
本地进程监督。账户、领养、聊天、Nest 规则和 Elfie 认知都不属于这一层。

## 启动与退出顺序

`src/main.ts` 先取得单实例锁，再通过
`src/platform/supervisor_config.ts` 解析开发态或安装包内的运行资源。
`RuntimeSupervisor` 的启动顺序是：

1. 启动或连接 Ollama，并等待 `/api/tags` 可用；
2. 启动 Python Core，并等待 `/api/health` 可用；
3. 在隐藏的、关闭后台节流的 `BrowserWindow` 中加载 Godot Web Runtime，
   注入本次启动生成的 runtime nonce 与 camera token，等待握手完成；
4. 打开同源 `/login` 登录窗口；登录后由 Core 按角色跳转到 `/chat` 或 `/manage`。

退出时先关闭隐藏 Godot Runtime，再停止 Python Core 和由 Desktop 管理的
Ollama。任一组件启动失败都会停止已经启动的组件，并显示归因到具体组件的错误
窗口。设置 `ELFIENEST_OLLAMA_EXTERNAL=1` 时，Desktop 不创建 Ollama 进程，但仍
会等待配置的 Ollama 地址可用。

## 资源发现

开发态可以通过以下环境变量显式指定资源，不需要把本机调试程序复制进源码：

- `ELFIENEST_CORE_BIN`、`ELFIENEST_CORE_CWD`：Python Core 程序与工作目录；
- `ELFIENEST_OLLAMA_BIN`、`ELFIENEST_OLLAMA_URL`：Ollama 程序与服务地址；
- `ELFIENEST_UI_URL`、`ELFIENEST_GODOT_URL`：管理界面与 Godot Web 入口；
- `ELFIE_HOME`：本次桌面运行使用的数据目录。

安装包资源按单一 target 放在
`build/staging/<platform-arch>/resources/`。资源清单实现支持：

- `darwin-arm64`
- `darwin-x64`
- `win32-x64`
- `linux-x64`

每个 target 必须包含 Godot Web 的 `html/js/wasm/pck`、三个产品页面的 Vite `web/`
构建产物、对应平台的 Python Core 和 Ollama 可执行文件。Python Core 在安装包内以
`python-core/ElfieNestCore`（Windows 为 `.exe`）被解析，并通过
`ELFIENEST_WEB_BUILD_DIR` 读取 `web/`；二者必须与资源清单采用同一相对路径。
`src/resources/resource_manifest.ts` 会记录文件大小和 SHA-256，并拒绝缺失资源。完整 staging 约定见
[`packaging/runtime-resources.md`](packaging/runtime-resources.md)。

内测安装包固定为 `0.1.0`，使用 `ElfieNest-0.1.0-internal-*` 命名，不配置
publish 或自动更新。macOS 和 Windows 的首次内测包不签名、不公证；测试者必须在
受控设备上确认系统来源警告，再进行安装、启动、健康检查和退出验收。

## 开发命令

需要 Node.js 20 和仓库锁定的 pnpm 10.12.1：

```bash
cd desktop
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
npx --yes pnpm@10.12.1 test
```

`scripts/assemble_desktop_resources.py` 在组装 staging 时会生成 `manifest.json`。
Desktop 启动时会在创建任何受管子进程前重新校验该清单；可用原有命令单独重建
用于诊断的清单：

```bash
cd desktop
ELFIENEST_TARGET=darwin-arm64 \
  npx --yes pnpm@10.12.1 build-resource-manifest
```

`npx --yes pnpm@10.12.1 dev` 会编译并启动 Electron，可能继续启动本地组件；
只做静态检查时不要用它。`npx --yes pnpm@10.12.1 package` 生成安装包，输出
只能进入根目录 `dist/`。

## 构建边界

```text
build/components/desktop/                         TypeScript 编译结果
build/staging/<platform-arch>/resources/          单平台打包资源
dist/                                             最终安装包
```

不要把生成的 JavaScript、Godot Web Runtime、Python Core、Ollama、模型或用户
数据写回 `desktop/`。改变资源布局或监督顺序时，应同步更新对应 TypeScript 测试、
本文件和 Developer 文档。
