# Desktop

Electron Desktop 是宿主和监督层，不是产品业务层。

Desktop 窗口固定先打开 Core 的 `/login`。登录后的 `/chat` 或 `/manage` 由 Core
根据会话角色和 Owner 的个人默认页决定；Electron 不复制任何登录、聊天或管理页面。

## 负责

- 单实例窗口与生命周期；
- Python Core、Ollama、Godot Web Runtime 的资源发现和进程监督；
- 平台路径、打包资源和退出收束；
- Desktop 端与 Web Runtime 的宿主桥接。

## 不负责

- Elfie 认知、人格、记忆和输出路由；
- 账户、领养、聊天和 Nest 规则；
- 复制 Python 或 Godot 的领域事实。

修改 Desktop 后，使用 `desktop/` 自己的锁文件和测试，不把 Desktop 生成物写回源码
目录。

开发时可运行：

```bash
cd desktop
pnpm install --frozen-lockfile
pnpm test
```
