# 架构 Scanner 执行规则

本目录实现长期架构契约的机器可证明部分，受根规则、仓库治理契约和
`test/architecture/AGENTS.md` 共同约束。

- Scanner 输出必须稳定、精确到文件与违规点，并映射到契约注册表中的长期契约；仍有
  临时债务时才关联 Conformance ID。禁止宽泛 allowlist、静默忽略或基于当前分支
  自我放行。
- `exact` 用于候选代码与候选 Baseline 精确对账，`subset` 用主分支 Scanner 证明候选
  没有新增债务，`deny-all` 用于基线清零后的永久零容忍状态。
- 修改规则、Registry、分类器或 CI 调用方式属于治理变更，不得混入生产源码。
  产品迁移只能删除已有 Baseline 条目，不能改 Scanner 来让实现通过。
- 生产根目录按路径分类，非文档文件都算产品源码，包括配置、脚本、Godot 资源和静态
  资产；不得退回源码后缀 allowlist。治理变更不得修改旧 Baseline，产品迁移只能缩减
  条目，已有治理契约后禁止新建 Baseline。
- Scanner、架构测试或治理 CI 变化必须带双语 ADR 更新；Pull Request 与受保护分支
  Push 都要使用基础提交中的不可变 Scanner 检查候选代码。
- 注册表不得保留全 closed Conformance 或空 Baseline；最后一个债务清零后，治理收口
  必须删除临时产物和绑定，并保留 Scanner 的 deny-all 门禁。
- Scanner 必须同时有正向和违规 Fixture 测试；路径迁移时规则表达所有权和依赖，
  不把临时旧目录写成永久必须存在的目标。
- 不读取生产数据、不启动服务、不依赖网络；同一输入必须产生同一排序输出和退出码。
