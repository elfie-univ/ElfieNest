# 构建与发布

## 构建目录

```text
build/  可再生中间构建产物，不提交
dist/   最终发行物，不提交
docs/.vitepress/dist/  VitePress 构建产物，不提交
```

Godot Web、Desktop JavaScript 和 Python Core 的生成结果必须进入对应构建目录，不
写回源码目录。

## 文档站

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
DOCS_BASE=/ npx --yes pnpm@10.12.1 build
```

GitHub Pages 使用 `/ElfieNest/` base。Pull Request 只构建；只有经过负责人审阅并
进入 `main` 的提交才允许进入 Pages 部署 job。

## 发布门

发布前必须确认：

1. 代码、测试和文档事实一致；
2. Gitleaks、质量基线和架构测试通过；
3. 公开页面没有私有世界观、合作材料和未审阅截图；
4. 用户完成页面目视验收；
5. 再由负责人决定何时提交、推送和部署。

## 0.1.0-beta.1 内测桌面安装包

当前只构建内部测试安装包：版本固定为 `0.1.0-beta.1`，不配置自动更新，也不打包任何
模型权重。每个平台必须在对应原生 runner 上构建：macOS
ARM64、macOS x64、Windows x64、Linux x64。安装包不包含 Ollama 引擎或模型，也不
创建私有 sidecar；公共 Ollama 是 Setup 中可选的用户决策。

发布协调器始终请求完整四 target 矩阵：`darwin-arm64`、`darwin-x64`、`win32-x64`、
`linux-x64`。每个 target 必须由匹配的原生 runner 构建并完成安装 smoke；缺少 runner
只能报告 `incomplete`，不能伪造跨平台成功。所有中间物都在 `build/`，最终安装包只在
`dist/`：

原生 target 使用 macOS `PKG`、Windows `NSIS` 和 Linux `DEB`。各安装器钩子会把包内管理
CLI 暴露为全局 `elfienest` 命令，并且只移除当前安装所拥有的 launcher。

原生 runner 会通过 `scripts/release.py --run-install-smoke` 调用
`scripts/release_install_smoke.py`。每个有界循环都会安装安装包、通过全局 launcher
启动、等待 `CORE_READY`/`WORLD_READY`、停止到 `OFFLINE`、再次安装同一个包验证升级，
最后卸载并证明所选 `ELFIE_HOME` 仍然保留。输出 JSON 包含带类型的安装/启动/健康/停止/
升级/卸载耗时和预算，Workflow 会把它和安装包一起上传。不带
`--run-install-smoke` 的本地构建不会修改主机安装环境。

```bash
# 构建当前原生 target；只在本地 build/dist 生成，不上传或发布
.venv/bin/python scripts/release.py --target darwin-x64

# 只在一次性原生发布 runner 上运行；同时执行安装/升级/烟测/卸载。
.venv/bin/python scripts/release.py --target darwin-x64 --run-install-smoke \
  --smoke-evidence-output dist/ElfieNest-darwin-x64-install-smoke.json

# 请求完整矩阵；不可用 runner 保持 incomplete
.venv/bin/python scripts/release.py
```

仓库内的 `.github/workflows/release.yml` 是多平台发布 Pipeline。它分别使用
macOS arm64、macOS Intel、Windows x64 和 Linux x64 的原生 GitHub runner。手动运行
`workflow_dispatch` 会构建四个安装包并保存为 Actions artifacts；推送与项目版本一致
的 tag（例如 `v0.1.0-beta.1`）会运行同一套矩阵，校验各平台安装包内容，并把四个安装包、
每个平台的 typed install-smoke JSON、`SHA256SUMS` 和 Release `manifest.json` 发布到
GitHub Releases。带预发布后缀的 tag
会被标记为 GitHub Pre-release；手动运行只有在开启
`publish_release` 且填写匹配的 `release_tag` 时才会创建 Release。
默认模式是未签名内部预览：Tag 推送不需要 Apple 凭据，macOS 产物文件名保留
`internal`，GitHub Release 一律标记为 Pre-release，并明确提示 macOS 未签名。

当前版本的正常发布命令是：

```bash
git tag -a v0.1.0-beta.1 -m "ElfieNest 0.1.0-beta.1"
git push origin v0.1.0-beta.1
```

上面的普通 Tag 命令发布未签名内部预览，不读取 Apple Secrets。本地执行
`scripts/release.py` 也采用相同的内部预览策略。安装包可以正常安装测试，但 macOS
仍可能显示 Gatekeeper 或“正在验证”提示。

正式签名只能显式开启：手动运行 Workflow，打开 `formal_macos_release`，填写匹配的
`release_tag`；需要创建 GitHub Release 时再同时打开 `publish_release`。只有这条正式
路径才要求 Developer ID 两套身份和 App Store Connect 公证凭据；缺失时 fail-closed，
凭据完整时校验 PKG、Gatekeeper、装订票据、完整 App、Python Core、管理 CLI 和嵌套
Mach-O 签名。

### macOS 签名与公证凭据

Apple Developer Program 的 Account Holder 需要分别创建一张用于 App 的
**Developer ID Application** 证书和一张用于 PKG 的 **Developer ID Installer**
证书；Apple 在 [Developer ID 证书说明](https://developer.apple.com/help/account/certificates/create-developer-id-certificates)
中区分了这两种用途。把证书及其私钥安装到钥匙串后，分别导出成带密码的 PKCS#12
（`.p12`）文件；GitHub Actions 中只保存文件的 Base64 内容和对应密码。

公证使用 App Store Connect 的**团队 API Key**；个人 API Key 不能供 `notarytool`
使用。私有 `.p8` 文件只能下载一次，必须放在仓库之外安全保存。具体入口见 Apple 的
[API Key 创建说明](https://developer.apple.com/documentation/appstoreconnectapi/creating-api-keys-for-app-store-connect-api)。

在仓库的 Actions secrets 中配置：

| Secret | 内容 |
| --- | --- |
| `MACOS_APPLICATION_CERTIFICATE` | Developer ID Application `.p12` 的 Base64 |
| `MACOS_APPLICATION_CERTIFICATE_PASSWORD` | 该 `.p12` 的密码 |
| `MACOS_INSTALLER_CERTIFICATE` | Developer ID Installer `.p12` 的 Base64 |
| `MACOS_INSTALLER_CERTIFICATE_PASSWORD` | 该 `.p12` 的密码 |
| `APPLE_API_KEY_BASE64` | 团队 `AuthKey_*.p8` 文件的 Base64 |
| `APPLE_API_KEY_ID` | App Store Connect Key ID |
| `APPLE_API_ISSUER` | App Store Connect Issuer ID |

Workflow 只把 `.p8` 解码到 runner 临时目录，并把两份 `.p12` 分别映射给
electron-builder 的 App 与 Installer 证书入口。它会启用 Hardened Runtime，向 Apple
公证 App 和 PKG，并装订返回的票据。凭据文件和 secret 值都不得提交进仓库。

每个安装包包含 Electron、前端、Godot Web、目标原生 Python Core 和管理 CLI。
最终用户只安装这些平台原生产物；源码 checkout 仍然只是开发环境。

GitHub 默认产物属于内部预览，macOS 包未签名且不承诺已公证；Windows 预览包也可能
显示发布者警告。缺少 Apple 凭据只会阻断显式选择的正式 macOS 发布。交付前仍须记录
“安装、启动、`/api/health` 成功、退出后子进程不存在”四项安装测试证据。
