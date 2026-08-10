# ADR-0004：App 业务域与纵向迁移切片

- **状态：** 已接受
- **日期：** 2026-08-10
- **范围：** `app/` 业务所有权与迁移单元

## 背景

App 与系统契约已经定义依赖方向、Ports/Adapters、Infrastructure 能力包、API 资源范围
和组合根，但当前 `app/features/` 与 `app/orchestration/` 目录仍是迁移期现状盘点，不是
最终业务地图。目录中存在按角色归组、空壳、所有权重叠和平铺工作流。机械照搬这些目录，
只会把原有歧义换一个位置继续保留。

ElfieNest 采用增量迁移，每个合入切片都必须保持产品可用。按物理层横向移动会留下半条
调用链，也无法判断何时可以删除旧实现。因此在产品迁移开始前，必须先固定最终业务单元
和工作流单元。

## 决策

App 迁移采用纵向切片。每个获批切片盘点真实 Interface 与调用方，建立唯一 Feature
公开门面，只定义该切片实际需要的 Port，在既定 Infrastructure 能力包中实现 Adapter，
由 Bootstrap 装配，迁移全部调用方，并在关闭切片前删除被替代实现。

最终 Feature 业务域为：

- `accounts`、`adoption`、`communication`、`elfies`、`nest_management`、
  `setup`、`bodies`、`operations`；
- `configuration`，其下以 `providers`、`food`、`capabilities`、`settings`
  作为可独立迁移的子域。

最终 Orchestration 工作流为 `lifecycle`、`nest_session`、
`resident_admission`、`setup_installation`、`message_delivery`、`embodiment`
和 `observer`。这些目录按真实跨 authority 工作流命名，不机械镜像每个 Feature。

`administration`、`chat`、`elfie_profile`、`nest_registration` 以及当前 Feature 层的
`embodiment` 都是迁移期位置。其现有行为由应用契约指定的最终所有者吸收；本决策不新增
任何产品能力。

API 继续版本化并按外部业务资源组织。Infrastructure 继续按系统契约中的七个能力包
组织，不镜像 Feature。Bootstrap 仍是唯一组合根，不是业务层，也不是独立横向迁移阶段。

## 后果

应用架构契约是规范性目标地图。应用架构一致性台账负责把当前位置映射到目标，并为每个
获批切片记录调用方、删除门和机器债务。只有对应切片开始时才创建目标目录；本决策不批准
空占位目录、猜测性 Port 方法、兼容层、功能扩张或全仓一次性搬迁。

本次拒绝把当前目录盘点当成最终结构、按页面或角色组织 Feature、在 Orchestration 或
Infrastructure 中逐 Feature 镜像、按物理层横向迁移，以及在盘点真实调用链前冻结完整
执行顺序。
