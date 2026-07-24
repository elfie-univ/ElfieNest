# 运行第一座 Nest

## 最小运行

在仓库根目录执行：

```bash
.venv/bin/python main.py
```

这个入口会准备一个最小 Nest，推进三次环境 tick，让 Elfie 经过一次感知—决策—输出
流程，然后主动结束本地服务。

## 你会看到什么

运行链路包含：

1. Nest 推进环境时间；
2. 身体与通信事件进入感知工作区；
3. BrainCoordinator 组织一次认知回合；
4. OutputRouter 将 DecisionPlan 分别路由到身体、通信或内部执行器；
5. 执行回执回到下一轮感知。

## 常用入口

```bash
./elfienest.sh serve --fallback
./elfienest.sh status
./elfienest.sh stop
```

完整命令和 Developer Tools 见[命令参考](/developer/tooling)。
