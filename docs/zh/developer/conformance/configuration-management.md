# 配置管理一致性

> 本文是规范性[配置管理契约](../contracts/configuration-management)的开放迁移台账，
> 只记录当前实现事实和删除门，不授权新增散落配置或产品行为。

**状态：** open

## 当前清单

当前登记的八份内置 YAML 已全部位于仓库根 `config/`：系统配置、Provider 与模型目录、
工具、Brain Energy、Selfhood、情绪表达以及 Nest 默认值。物种/Profile 声明明确不进入本次
迁移。算法常量、构建配置与协议常量不进入本次迁移，除非契约分类规则明确把它们识别为
产品配置。

领域类型和 Adapter 中保留的少量直构安全默认值不是打包产品文档；生产组合根会加载登记
文档并注入强类型值。

现有用户路径 resolver 和原子 YAML 写入器已经指向 `${ELFIE_HOME}/configs/`，首次运行
目录创建也不会复制默认值；迁移必须保留这些已经符合目标的行为。

## 开放缺口

| ID | 严重度 | 状态 | 当前偏差 | 收口门 | 证据 |
| --- | --- | --- | --- | --- | --- |
| CFG-001 | P0 | open | 本次范围内默认值已迁移到根 `config/`；旧 Provider/模型/Brain 包内 YAML 与 Python 字面量模型目录已删除，生产消费方改用登记加载器或注入的强类型值。 | 完成完整清单并证明没有未分类的范围内残留；不得触碰 Profile 物种声明或新增能力。 | 代码：`config/`、已删除旧 YAML、`infrastructure/persistence/configuration/bundled_defaults.py`、`infrastructure/models/catalog.py`；完整清单证据待记录 |
| CFG-002 | P0 | open | 封闭注册表、内置/用户配置源、文档策略和永久负向架构检查均已存在；完整策略验收矩阵与收口证据仍待记录。 | 证明字段覆盖、整文档替换、仅内置、仅用户、失败与 Secret 规则，并清除业务/领域 YAML 和任意路径访问。 | `infrastructure/persistence/configuration/documents.py`、`test/architecture/test_configuration_management.py`；聚焦测试已通过，完整矩阵待完成 |
| CFG-003 | P0 | open | Desktop staging 只复制一次根 `config/` 到 `resources/config/`；已删除 package-data 和旧目录副本；发行 manifest 要求八份文档。 | 证明 manifest 哈希完整、无源码 checkout 的安装态启动，以及用户配置保留。 | `scripts/assemble_desktop_resources.py`、`scripts/release_manifest.py`、安装态测试；完整矩阵待完成 |
| CFG-004 | P1 | open | 配置专用永久结构和边界检查已经登记到 Contract Registry，并以 deny-all 形式运行；五类收口证据尚未记录。 | 完成五类收口证据，并保留永久目标检查的 deny-all 模式。 | `scripts/architecture/contract_registry.py`、`test/architecture/test_configuration_management.py`；最终审计待完成 |

## 收口顺序

1. 冻结并分类本次范围内完整的源码默认值、路径和打包清单；把 Profile 物种声明记录为范围外。
2. 完成聚焦策略和边界验收矩阵，不新增产品行为。
3. 为每一行记录五类证据，只关闭残留清单为空的行。

全部行具备完整证据并标记 ready 后，再以独立治理收口删除本台账。产品迁移不能删除
或削弱本台账、契约及其永久检查。
