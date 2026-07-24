# 调试与实验台

## Elfie Lab

用于观察单个 Elfie 的档案、感知、认知回合和输出投影。它拥有独立入口、端口和
数据目录，不进入普通用户导航。

## Nest Lab

用于验证巢内状态、环境时钟、互动传播和 Godot 语义边界。它不创建完整 Elfie，
也不复制 Godot 房屋几何。

## Runtime Lab

用于检查 Provider、模型配置、粮食策略、工具和安全策略。它是命令行实验台，不是
普通用户产品页面。

## 隔离运行

```bash
./developer.sh elfie-lab --data-dir /tmp/elfienest-elfie-lab --port 8877
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab --port 8890
./developer.sh runtime-lab --config-dir /tmp/elfienest-runtime-lab show
```

实验必须使用临时 `ELFIE_HOME` 或显式数据目录；调试完成后检查没有遗留进程、端口、
缓存或生成文件。
