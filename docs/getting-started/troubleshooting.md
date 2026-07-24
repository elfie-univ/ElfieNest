# 故障排查

## 命令找不到 `uv`

先按 uv 官方说明安装，再重新运行：

```bash
./install.sh --env-only
```

## Python 版本不对

项目固定使用 CPython `3.9.25`。不要复用其他虚拟环境，重新运行安装器即可。

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

先用回退模式验证基础链路：

```bash
./elfienest.sh serve --fallback
```

如果回退模式正常，再检查 Ollama 地址、Provider 配置和环境变量。

## 数据目录异常

给本次实验设置独立 `ELFIE_HOME`，不要删除默认数据目录：

```bash
ELFIE_HOME=/tmp/elfienest-debug .venv/bin/python main.py
```
