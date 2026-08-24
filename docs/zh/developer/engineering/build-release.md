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
CLI 暴露为全局 `elfienest` 命令。POSIX 钩子只有在现有命令是同一软件包拥有的精确符号
链接时才允许复用，否则会报告冲突而不会覆盖；移除钩子也只删除精确匹配的软件包 launcher。
Windows 只在当前用户 PATH 中增加和删除本次安装目录对应的精确项。

原生 runner 会通过 `scripts/release.py --run-install-smoke` 调用
`scripts/internal/release/release_install_smoke.py`。每个有界循环都会安装安装包、通过全局 launcher
启动、必须到达 `WORLD_READY`、停止到 `OFFLINE`、再次安装同一个包验证升级，
最后卸载并证明所选 `ELFIE_HOME` 仍然保留。输出 JSON 会记录已到达的 `WORLD_READY`，并包含带类型的安装/启动/健康/停止/
升级/卸载耗时和预算，Workflow 会把它和安装包一起上传。不带
`--run-install-smoke` 的本地构建不会修改主机安装环境。
smoke runner 会在首次清理前从 DEB 读取 Linux 软件包名，不会无条件删除全局 launcher。

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
发布到 GitHub Releases。每个平台的 typed install-smoke JSON 只保留在 Actions 构建产物中
作为 CI 证据，不作为 Release 下载项展示。带预发布后缀的 tag
会被标记为 GitHub Pre-release；手动运行只有在开启
`publish_release` 且填写匹配的 `release_tag` 时才会创建 Release。

当前版本的正常发布命令是：

```bash
git tag -a v0.1.0-beta.1 -m "ElfieNest 0.1.0-beta.1"
git push origin v0.1.0-beta.1
```

Workflow 会在各平台校验安装后的资源布局，但当前内测包仍未签名或公证。交给测试者
之前，仍必须按上面的发布门记录完整的安装、启动、`/api/health` 和干净退出证据。

每个安装包包含 Electron、前端、Godot Web、目标原生 Python Core 和管理 CLI。
最终用户只安装这些平台原生产物；源码 checkout 仍然只是开发环境。

首次内测的 macOS、Windows 安装包没有签名或公证，系统会显示来源警告；这是当前
内测约束，不应通过关闭安全机制来绕过。安装测试必须记录“安装、启动、`/api/health`
成功、退出后子进程不存在”四项结果后，才可交给下一位测试者。
