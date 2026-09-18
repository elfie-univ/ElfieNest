---
name: brain-trace-collector
description: 通过 Developer Tools 后端采集一次真实 Brain 链路的结构化中间数据；支持真实或模拟模型、真实或模拟记忆，不负责分析、评分或 UI。
---

# Brain Trace Collector

这个技能只负责采集证据。它调用仓库内的 `developer.sh brain-trace`，让现有 Brain、Memory、Reasoning、Settlement 和持久化链路真实运行，并返回本地 artifact 路径。它不启动前端、不调用 `brain-eval`，也不解释采集结果。

## 使用流程

1. 先列出隔离 Developer Tools 数据根中的 Elfie 和 saved Food：

   ```bash
   ./developer.sh brain-trace list --data-dir <elfie-lab-data-dir>
   ```

2. 根据用户明确选择的模式调用采集器。`--model real` 时必须传入已保存的 `--food-key`；`--model mock` 使用确定性模型。`--memory mock` 可以传 typed fixture；不传时使用空的真实 Memory store。

   ```bash
   ./developer.sh brain-trace collect \
     --data-dir <elfie-lab-data-dir> \
     --elfie-id <id> \
     --memory real|mock \
     --model real|mock \
     --food-key <saved-food> \
     --messages-file <messages.jsonl> \
     --memory-fixture <memory.json> \
     --output-root build/brain-trace
   ```

3. 把命令输出中的 `artifact_dir` 和 `manifest.json` 状态返回给用户。需要诊断时，另行读取 artifact；本技能不产生 score、verdict、recommendation 或其他分析字段。

## 硬边界

- 只使用隔离 Developer Tools 数据根，拒绝生产 `ELFIE_HOME`。
- 真实 Memory 运行在 Elfie 快照副本中，不能修改源 Elfie。
- 真实 Provider 必须由用户选择并显式授权；失败必须保留错误和 partial artifact，不能静默切换 mock。
- 凭据、Authorization、API key 和 token 必须脱敏；artifact 只写本地忽略目录。
- 不启动 Web UI、不修改产品服务、不创建第二套 Brain、不调用评测裁判。
