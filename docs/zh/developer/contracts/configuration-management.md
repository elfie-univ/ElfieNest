# 配置管理契约

**契约版本：** 1.2
**采用日期：** 2026-08-15
**适用范围：** 应用默认配置、用户配置、读取与发行打包

> **规范性目标。** 本契约定义 ElfieNest 唯一的配置管理方式，只整理现有配置，
> 不新增产品能力。当前实现差距只记录在
> [配置管理一致性台账](../conformance/configuration-management)中。

## 目标与边界

ElfieNest 只有两个持久配置根：

```text
仓库 config/                        ${ELFIE_HOME}/configs/
随版本管理的内置默认配置            用户拥有的运行时配置
应用运行时只读                      通过强类型应用 Port 写入
        |                                      |
        +----------- 强类型文档加载器 ---------+
                              |
                         有效强类型配置
```

源码根固定使用小写、单数的 `config/`；现有用户根继续使用小写、复数的
`configs/`。二者的所有者和生命周期不同，不能当成同一目录的两份副本。

用于定位资源、拒绝非法配置或报告启动失败的少量常量可以保留在代码中，但它们不是
第三层配置，也不能复制产品默认值。必需的内置产品数据缺失时，不能静默回退到另一份
硬编码副本。

本契约管理应用配置。`pyproject.toml`、CI、Electron Builder 和 Godot 工程文件等
构建工具配置继续归各自工具所有。协议常量、算法不变量、派生值，以及必须经过代码
审查才能改变的安全限制，仍保留在代码中；除非另一个已批准变更明确把它们归类为
产品配置。

## 物理目录

首轮内置默认配置清单如下：

```text
config/
├── app/
│   └── system-defaults.yaml
├── models/
│   ├── provider-catalog.yaml
│   └── model-catalog.yaml
├── tools/
│   └── defaults.yaml
├── brain/
│   ├── energy.yaml
│   ├── selfhood.yaml
│   └── emotion-expressions.yaml
├── nest/
    └── defaults.yaml
└── species/
    ├── catalog.yaml
    └── <package>/
        ├── species.yaml
        ├── appearance.yaml
        ├── genesis.yaml
        └── assets/*.png
```

这棵目录是内置默认值和物种配置包的来源。`species/catalog.yaml` 是已注册文档；
其余包成员由 Infrastructure Adapter 作为一个不可变物种包统一校验。Profile 和
Genesis 只接收类型化值，不读取 YAML。Godot 的 3D 资源包仍位于
`godot_project/characters/`；物种配置只保存它的语义链接和外观绑定。

用户目录保持为：

```text
${ELFIE_HOME}/configs/
├── runtime.yaml
├── providers.yaml
├── tools.yaml
├── provider-catalog.yaml
├── auth.env
└── credentials/
    └── oauth/
        └── <connection_id>.json
```

`auth.env` 与 OAuth 文档属于密钥，不是可合并默认配置。它们因为归用户所有而位于
用户根目录，但仓库 `config/` 下禁止存在对应源码文件。

## 文档注册、所有权与 Schema

每份获准配置文档都必须有一条封闭的 `ConfigDocumentSpec` 等价定义，明确：

- 稳定文档 ID 与语义所有者；
- 内置和/或用户相对路径；
- 内置文档是否必需；
- 文档版本与强类型校验器；
- 有效值策略；
- 写入、重载与失败策略。

生产调用方只能选择已知文档 ID，不能传入任意文件系统路径或点分键。测试和开发工具
可以注入隔离的沙箱根目录以保证测试确定性，但 Adapter 仍然只能选择同一份已注册文档
和固定相对路径，并且绝不能默认指向生产 `${ELFIE_HOME}`。新增文档必须同时提供所有者、
Schema、策略、测试和发行覆盖。文档注册表不是插件注册表。

语义所有者定义严格模型与校验规则；Infrastructure 配置 Adapter 负责路径解析、解码、
合并执行、原子文件 I/O 和技术错误。把文件物理放进 `config/`，不会把 App、Elfie、
Nest、模型或工具语义转交给 Infrastructure。

| 有效配置 | 内置来源 | 用户来源 | 语义所有者 | 策略 |
| --- | --- | --- | --- | --- |
| 系统设置 | `app/system-defaults.yaml` | `runtime.yaml` 中归其所有的 section | App 配置设置 | 按 Schema 字段覆盖 |
| Provider 产品目录 | `models/provider-catalog.yaml` | `provider-catalog.yaml` | Infrastructure Models 元数据 | 校验通过后整文档替换 |
| 模型元数据目录 | `models/model-catalog.yaml` | 无 | Infrastructure Models 元数据 | 仅内置 |
| 全局工具设置 | `tools/defaults.yaml` | `tools.yaml` | App 配置能力 | 按工具、按字段覆盖 |
| Energy 创建期默认值 | `brain/energy.yaml` | 无 | Elfie Brain Energy | 仅内置 |
| Selfhood 创建期默认值 | `brain/selfhood.yaml` | 无 | Elfie Brain Selfhood | 仅内置 |
| 情绪表达映射 | `brain/emotion-expressions.yaml` | 无 | Elfie Brain Emotion | 仅内置 |
| Nest 初始化默认值 | `nest/defaults.yaml` | 无 | Nest | 仅内置 |
| 物种目录和物种包 | `species/catalog.yaml`、`species/<package>/` | 无 | Infrastructure 加载器，类型化值注入 Profile/Genesis/Adoption | 仅内置 |
| Provider 连接与 endpoint 模型 | 无 | `providers.yaml` | App 配置 Provider | 仅用户 |
| API 与 OAuth 凭据 | 无 | `auth.env`、`credentials/oauth/` 或进程环境 | Secret 能力 | 仅用户，绝不合并 |

每份 YAML 文档都包含明确的顶层文档版本。代码类型是机器可读 Schema 的权威；本契约
不再创建一份重复 JSON Schema。任何值暴露给消费方前，先完成版本校验。

现有 `runtime.yaml` 还包含明确声明的透明兼容桶，供其他当前消费者使用：
`runtime_policy`、`models` 以及未归本设置 Adapter 所有的 `system` section。Settings
Adapter 只保留这些桶，不解释也不扩展它们；已拥有的设置 section 仍然严格校验。

## 加载边界

实现必须提供等价于以下角色的能力：

```text
BundledConfigSource       RuntimeConfigSource
读取内置配置根            读写 ELFIE_HOME/configs
          \                 /
             文档专用强类型 Adapter
             校验 + 执行已声明策略
                         |
        SystemSettings / ProviderCatalog / ToolSettings /
        Brain 默认值 / Nest 默认值
```

具体规则如下：

- 开发环境从仓库根 `config/` 解析内置文档；
- 安装后只能从启动器/资源 resolver 提供的 `resources/config/` 解析；
- 安装后不能把当前工作目录或源码 checkout 当作回退路径；
- `infrastructure/persistence/configuration/` 是全局配置文件的运行时技术边界；
- 构建和发行校验器可以读取 `config/` 做校验与复制，但不能成为运行时配置源；
- App Feature、Interface、Orchestration、Elfie 与 Nest 不解析这些根目录、不导入 YAML
  解析器，也不直接读取配置文件；
- Bootstrap 只构造并注入配置源或强类型结果，不解析、不合并、不复制，也不拥有配置
  事实；
- 消费方只能收到命名强类型值，不能收到通用嵌套字典、任意 section API 或 Service
  Locator。

仅内置的静态值可以在构造时直接注入。只有消费方确实需要可替换读写时才建立 Port；
本契约不要求为每个不可变值机械复制一层 Protocol。

## 优先级与合并语义

“用户配置覆盖内置默认值”只是单份文档已声明策略的简写，不授权建立全仓通用深合并。

对按 Schema 字段覆盖的文档：

- 用户文档或字段不存在时使用内置值；
- 用户提供且通过校验的标量替换内置标量；
- 映射只沿该文档 Schema 明确拥有的字段合并；
- 明确声明的透明扩展桶可以保留其他已注册消费者拥有的数据，但已拥有的 section 仍然
  必须严格校验；
- 用户列表默认整体替换内置列表，除非该文档明确声明按键列表策略；
- `null` 只对 Schema 明确允许为空的字段成立，不是通用删除标记；
- 未知字段默认拒绝，除非强类型 Schema 明确拥有扩展字段；
- 文档版本元数据独立校验，绝不参与合并。

Provider 目录有意采用不同策略：通过校验的用户目录整体替换内置目录。Provider 连接
是纯用户事实，不能从内置连接模板生成。Secret 只能从进程环境或用户密钥存储解析，
绝不进入 YAML 合并逻辑。

## 缺失、损坏与配置变化

| 情况 | 必须行为 |
| --- | --- |
| 必需内置文档缺失、损坏或版本不支持 | 构建校验或启动失败，报告文档 ID 和安全诊断；不能使用重复代码默认值 |
| 可选用户文档缺失 | 视为没有用户值；不能创建默认副本 |
| `runtime.yaml`、`providers.yaml` 或 `tools.yaml` 损坏 | 拒绝受影响的强类型读取或写入；不能部分应用 |
| 用户 `provider-catalog.yaml` 损坏 | 记录安全警告并使用已校验内置目录，保留现有整文档回退行为 |
| Secret 缺失 | 返回现有强类型 unavailable/not-configured 状态；不能插入占位密钥 |
| 文档版本未知或不兼容 | 按该文档的强类型失败策略拒绝；不能猜测或静默改写 |

写入器只能修改自己拥有的用户文档或 section，保留无关的已拥有数据，从普通 YAML
中移除明文 Secret，并采用同目录原子替换。是否备份可以按文档定义。读取不能顺手
修复、迁移或重写用户文件。

集中整理不新增全局文件监听或热加载。每份文档继续保留现有明确重载边界，除非另行
批准行为变更。

## 安装与升级生命周期

源码和安装后的解析路径是：

```text
开发环境：    <repository>/config/
发行环境：    <application>/resources/config/
用户写入：    ${ELFIE_HOME}/configs/
```

发行 staging 只包含一份内置配置：

```text
resources/
├── config/
├── web/
├── godot-web/
├── python-core/
├── management-cli/
└── manifest.json
```

发行组装必须校验每份已注册内置文档，只复制一次源码目录到 `resources/config/`，并把
每个文件的大小和哈希写入发行 manifest。Python 可执行文件与 package data 不能再
包含第二份权威副本。

首次运行只创建所需 `${ELFIE_HOME}` 目录，不把内置默认值复制到 `configs/`。用户文件
只由真实写入用例创建。应用升级只替换应用内置资源并保留用户配置；下一个已声明加载
边界重新计算有效值。

## 质量门禁与变更控制

实现开始前，治理层已经生效：

- 本双语契约固定目标；
- ADR-0017 和 ADR-0019 记录决策；
- Contract Registry 绑定契约、ADR、Agent 规则、机器治理测试与临时一致性台账；
- 一致性台账列出全部当前实现差距，但不削弱目标。

配置迁移只有在聚焦证据证明以下全部条件后才能收口：

1. 清单覆盖每个被迁移默认值、旧加载器、直接路径、package-data 条目和发行消费方，
   不保留未分类残留；
2. 架构检查拒绝包内局部默认配置、业务/领域直接读取 YAML、生产环境任意路径配置访问，
   以及本契约覆盖范围内的重复硬编码产品默认值；测试和开发工具可以使用注入的沙箱根；
3. 文档测试覆盖 Schema、版本、表中每种策略、缺失字段、列表、可空值、未知字段和
   损坏文档；
4. 持久化测试覆盖原子写、无关字段保留、Secret 排除、干净首次运行和用户文件保留；
5. 发行测试证明 `config/` 精确 staging、单副本打包、manifest 哈希完整，并且安装态
   在不存在源码 checkout 时可以启动；
6. 最终每行一致性收口都记录 `target`、`inventory`、`references`、`verification`、
   `residuals` 五类证据。

临时缺口清零后，永久检查以 deny-all 运行。放松路径、所有者、优先级、Secret 边界或
打包不变量，必须先升级双语契约版本并新增 ADR，再开始实现。普通配置新增也必须同时
更新封闭文档注册、强类型 Schema 和聚焦测试。

## 明确不做的事

本次整理不新增 Provider、模型、工具、Brain 或 Nest 能力；不新增文件系统自动发现、
配置驱动协议实现、公开任意配置 API、UI 字段、数据迁移、双读、双写、兼容别名、远程
配置或全局热加载。物种包注册固定由目录文件控制，并且仍必须配套完整 Godot 资源包
和代码拥有的运行时协议支持。
