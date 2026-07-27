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

Ollama 是可选能力。若在 Setup 中选择了它，请检查已保存的唯一 Ollama endpoint
及其 Provider 配置；不要扫描并切换到另一个本地服务。也可以在 Setup 中跳过它或
配置其他 Provider。

## 数据目录异常

给本次实验设置独立 `ELFIE_HOME`，不要删除默认数据目录：

```bash
ELFIE_HOME=/tmp/elfienest-debug .venv/bin/python main.py
```
