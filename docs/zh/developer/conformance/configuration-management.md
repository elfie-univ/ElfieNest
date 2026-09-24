# 配置管理一致性

> 本文是规范性[配置管理契约](../contracts/configuration-management)的已收口迁移台账，
> 只记录当前实现事实和删除门，不授权新增散落配置或产品行为。

**状态：** closed（CFG-006；v0.2 结构行保持关闭）
**收口状态：** closed

## Genesis 准备资料缺口

| ID | 严重性 | 状态 | 当前差距 | 关闭条件 | 证据 |
| --- | --- | --- | --- | --- | --- |
| CFG-006 | P1 | closed | 已发布的 `config/genesis/program.yaml` 及全部 18 个 manifest 成员，现为 Adoption 与 Genesis 唯一创建输入。旧 `config/world/` 和 `config/species/` 生产配置已移除；Myelle 仍为 draft。 | 保持单一经 manifest 校验的资料包、单一强类型消费路径、失败即关闭的可领养条件，并将运行时/Godot 资产分开；不得恢复双读或隐式来源回退。 | target=配置契约 1.7、应用契约 1.12、ADR-0039/0040；inventory=入口、18 个 manifest 成员、登记加载器、Adoption Bootstrap、发行 staging 和旧生产配置路径缺席；references=`documents.py`、`genesis_package_adapter.py`、`world.py`、`species.py`、`app_wiring/adoption.py`、`release_manifest.py`；verification=资料包完整性及 161 条知识/45 条条件检查、物种/地理/编译测试、版本化 Adoption 候选→提交 E2E 与已保存 Memory 检查、发行资源及封闭清单测试；residuals=Myelle 因单独的 Godot 资源门禁仍不可领养。 |

## 当前清单

当前登记的内置 YAML 已全部位于仓库根 `config/`：系统配置、Provider 与模型目录、
工具、Brain Energy、Selfhood、情绪表达、Nest 默认值，以及包含物种成员的版本绑定
Genesis 资料包。资料包成员由登记的 Adapter 动态发现并校验，不为每个未来物种增加封闭的
文档 ID，因此新增物种仍只需配置文件。算法常量、构建配置与协议常量不进入本次迁移，除非
契约分类规则明确把它们识别为产品配置。

领域类型和 Adapter 中保留的少量直构安全默认值不是打包产品文档；生产组合根会加载登记
文档并注入强类型值。

现有用户路径 resolver 和原子 YAML 写入器已经指向 `${ELFIE_HOME}/configs/`，首次运行
目录创建也不会复制默认值；迁移必须保留这些已经符合目标的行为。

## 已收口迁移台账

| ID | 严重度 | 状态 | 当前偏差 | 收口门 | 证据 |
| --- | --- | --- | --- | --- | --- |
| CFG-001 | P0 | closed | 本次范围内默认值只有一个根 `config/`；旧包内 YAML、重复模型目录数据与散落运行时读取已删除或完成归类。物种包注册在 `config/genesis/`，并且只由 Infrastructure Adapter 加载。 | 保持双根清单精确，并拒绝未归类的内置文件。 | target=two-root-source-inventory; inventory=`config/` 内置文档及 `config/genesis/` 资料包成员、用户 `configs/` 文档、旧路径、加载器、package data 与发行消费方；references=`infrastructure/persistence/configuration/documents.py`、`infrastructure/persistence/configuration/species.py`、`test/infrastructure/persistence/configuration/test_species.py`、`test/architecture/test_configuration_management.py`; verification=注册表清单测试、物种包测试与仓库/package 审计；residuals=zero |
| CFG-002 | P0 | closed | 注册表现在记录 Schema、写入、重载和失败元数据；内置源与用户源在暴露前校验，语义所有者拒绝自有字段中的未知字段，生产根由 resolver 所有。测试和开发工具明确保留注入沙箱根。 | 保持字段覆盖、整文档替换、仅内置、仅用户、失败、Secret 与生产路径规则由永久测试保护。 | target=registered-document-boundary; inventory=全部已注册文档 ID、严格 Schema、目录/连接语义校验器、Secret 边界与测试/开发沙箱入口；references=`infrastructure/persistence/configuration/documents.py`、`schemas.py`、模型/Provider 解析器、`test/infrastructure/persistence/configuration/test_documents.py`; verification=配置聚焦测试与架构测试；residuals=zero |
| CFG-003 | P0 | closed | Desktop staging 只把仓库 `config/` 复制一次到 `resources/config/`；发行 manifest 覆盖每个 staging 文件，用户配置不会被复制或覆盖；发行态解析必须由 launcher 提供资源根。 | 保持单份 staging、完整哈希、脱离源码 checkout 启动和用户文件保留。 | target=single-staged-bundled-root; inventory=资源组装、manifest 必需路径/哈希、发行态 resolver 与首次运行/用户写入行为；references=`scripts/internal/build/assemble_desktop_resources.py`、`scripts/internal/release/release_manifest.py`、`test/scripts/test_assemble_desktop_resources.py`、`test/scripts/test_release_manifest.py`; verification=组装、manifest、安装根与用户保留测试；residuals=zero |
| CFG-004 | P1 | closed | 双语契约、ADR、Contract Registry、Agent 规则和永久 deny-all 检查现在都与双根配置契约及明确的沙箱例外一致。 | 保持五类证据结构，并在后续治理专用删除前保留永久目标检查的 deny-all 模式。 | target=configuration-contract-closure; inventory=契约、ADR、Registry、Agent 规则、架构门禁与双语台账行；references=`docs/developer/contracts/configuration-management.md`、`docs/developer/decisions/0017-bundled-defaults-and-user-configuration.md`、`scripts/governance/contract_registry.py`; verification=治理架构测试与双语镜像检查；residuals=zero |
| CFG-005 | P0 | closed（v0.2 结构） | 已发布的 Genesis 资料包是唯一生效的创建资料源。Infrastructure 校验包完整性并投影强类型值；语义编译归 `elfie/genesis`。原 Profile Canon 来源已删除，Genesis 创建投影与运行时资产投影已分开，已提交精灵可脱离创建资料包恢复。 | 保持单一生效来源、Genesis 语义所有权和 Infrastructure 的 Schema/引用/包校验边界；Profile 不接收创建资料包或运行资产投影。 | target=配置契约 1.7、物种资源包契约 4、Elfie 2.6 与 ADR-0033/0040；inventory=`config/genesis/`、文档 registry/schema/loader、Genesis、Adoption 与运行时资产消费方；references=递归来源盘点、物种包测试、Genesis 编译测试、最终 Schema 测试和脱离创建资料恢复验收；verification=配置、架构、staging/reopen 与最终恢复测试；residuals=真实 workspace 数据政策由 SHD-007 单独跟踪。 |

## 收口顺序

1. 冻结并分类本次范围内完整的源码默认值、路径和打包清单，包括物种包成员。
2. 完成聚焦策略和边界验收矩阵，不新增产品行为。
3. 为每一行记录五类证据，只关闭残留清单为空的行。

全部行具备完整证据并标记 ready 后，再以独立治理收口删除本台账。v0.2
结构行已经关闭；未来世界资料内容修订和真实 workspace 数据政策仍是独立决策。
产品迁移不能删除或削弱本台账、契约及其永久检查。
