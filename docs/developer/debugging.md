# 调试与实验台

## Elfie Lab

用于观察单个 Elfie 的档案、感知、认知回合和输出投影。它拥有独立入口、端口和
数据目录，不进入普通用户导航。

## Nest Lab

用于验证固定房间中的巢内状态、角色入巢、Godot 语义边界和运行时事件。启动后会自动
打开本机网页：中央预览的是导出的 Godot 房间；右侧可调整床位、添加狐狸或小狗、开启
Python 驱动的随机游走，并暂停、继续或重置实验。事件时间线会显示世界配置、角色同步、
移动终态、碰撞和其他 Runtime 事实。

房屋几何、渲染、寻路和碰撞始终由 Godot 执行；Lab 不在 Python 复制坐标或物理规则。
随机游走只是 Python 每两秒选择一个语义锚点并发送既有 v2 移动命令，不是角色自主大脑。
直接启动即可；脚本会自动复用当前导出物，或在缺失、Godot 源码变化时用项目声明的 Godot
版本重新导出：

```bash
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab --port 8890
```

它不会悄悄启动正式产品引擎；Lab 仅启动隔离的 Godot Web Runtime 和对应的本地网关。

## Runtime Lab

用于检查 Provider、模型配置、粮食策略、工具和安全策略。它是命令行实验台，不是
普通用户产品页面。

## 隔离运行

```bash
./developer.sh elfie-lab --data-dir /tmp/elfienest-elfie-lab --port 8877
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab --port 8890 --godot-ws-port 8891
./developer.sh runtime-lab --config-dir /tmp/elfienest-runtime-lab show
```

实验必须使用临时 `ELFIE_HOME` 或显式数据目录；调试完成后检查没有遗留进程、端口、
缓存或生成文件。
