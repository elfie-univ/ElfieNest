# 安装配置

## 开始前先确认

你需要一台能够运行官方 ElfieNest 安装包的电脑。按自己的系统选择：

| 电脑 | 应选择的安装包 |
| --- | --- |
| Apple 芯片 Mac | macOS arm64 |
| Intel 芯片 Mac | macOS x64 |
| Windows 电脑 | Windows x64 |
| Linux 电脑 | Linux x64 DEB |

请只从[官方 Releases 页面](https://github.com/elfie-univ/ElfieNest/releases)下载。
预览版目前不会自动更新，升级前请先看对应版本的发布说明。

> **还没有安装包怎么办？** 项目仍处于预览发布阶段。不要为了运行 ElfieNest 而去
> 克隆源码或安装开发工具，请等待官方安装包，或向管理员索取已经确认过的安装文件。

## 安装应用

1. 下载与你的电脑匹配的文件。
2. 双击打开，并按系统的常规安装步骤操作。
   - macOS：打开 PKG，按安装器提示完成安装。
   - Windows：运行安装程序，除非管理员另有说明，否则保留默认安装位置。
   - Linux：使用系统软件包管理器安装 DEB。
3. 从“应用程序”“开始”菜单或桌面启动 **ElfieNest**。

第一次打开时，应用需要准备本地服务，可能会比平时多等一会儿。不要同时打开多个
ElfieNest 窗口。

macOS 和 Linux 安装器会把管理命令发布到 `/usr/local/bin/elfienest`。如果这里已经有
普通文件，或符号链接指向另一个程序，安装器会报告冲突并停止，不会覆盖原有命令。请先
确认原命令由谁管理，妥善移动或移除后再重新安装。

预览版 macOS 和 Windows 安装包可能会提示“未签名”或“未公证”。请先确认文件确实
来自官方 Releases 页面，不要为了来源不明的文件关闭电脑安全设置。

## 关闭窗口后为什么还在运行？

桌面应用关闭窗口后会把 ElfieNest 隐藏到后台，本地服务仍然可用，这样你可以继续用手机
访问而不必重新打开桌面窗口。想要彻底停止时，请在应用菜单或托盘菜单选择“退出 ElfieNest”。

## 如何卸载

移除应用不会删除 `ELFIE_HOME`（默认通常是 `~/.elfienest`）和 Nest 数据。如果还要删除
配置或数据，请在移除应用**之前**运行 `elfienest uninstall`，并选择对应的清理选项。
这个命令只处理数据，不会移除已经安装的应用。

- **Windows：**打开“设置 > 应用 > 已安装的应用”，选择 **ElfieNest** 后点击“卸载”。
  卸载器会移除自己安装的应用文件、命令 launcher 和 PATH 项。
- **Linux（DEB）：**运行 `sudo apt remove elfienest-desktop`。软件包只会删除仍然指向
  当前 ElfieNest 安装文件的 launcher。
- **macOS（PKG）：**macOS 没有统一的 PKG 卸载按钮，请运行下面的命令。只有 launcher
  仍然指向当前 ElfieNest 应用时才会将它移除：

  ```bash
  if [ "$(readlink /usr/local/bin/elfienest 2>/dev/null || true)" = "/Applications/ElfieNest.app/Contents/Resources/management-cli/ElfieNestCli" ]; then
    sudo rm -f /usr/local/bin/elfienest
  fi
  sudo rm -rf /Applications/ElfieNest.app
  sudo pkgutil --forget com.elfienest.desktop
  ```

如果这个 Nest 由多人使用，或你不确定数据是否应该保留，请先备份并询问 Nest 管理员，
再选择数据清理选项。

## 下一步

应用安装完成后，继续阅读[首次配置](./configuration)。
