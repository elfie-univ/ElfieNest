# 故障排查

## 命令找不到 `uv`

先按 uv 官方说明安装，再重新运行：

```bash
./elfienest.sh
```

## Python 版本不对

项目固定使用 CPython `3.9.25`。不要复用其他虚拟环境；源码开发运行
`./elfienest.sh`，完整安装当前机器应用运行 `./install.sh`。

## 端口已被占用

先查看当前项目登记的服务：

```bash
./elfienest.sh status
```

确认属于当前项目后再执行：

```bash
./elfienest.sh stop
```

不要使用宽泛的 `kill` 命令清理未知进程。

## 模型连接失败

本地 Ollama 是可选能力。Setup 阶段只显示“已安装”或“未安装”，真实健康检查会在最后
确认后进行。安装器会复用唯一的公共 Ollama；如果它已停止则尝试启动，启动或健康检查失败
则修复，完全不存在时才安装。不会创建第二个私有 Ollama 实例。

如果模型阶段失败，直接使用已锁定 Setup 页面上的重试操作。安装器会复查已完成阶段，不要求
重新填写配置。

## 数据目录异常

给本次实验设置独立 `ELFIE_HOME`，不要删除默认数据目录：

```bash
ELFIE_HOME=/tmp/elfienest-debug .venv/bin/python main.py
```
