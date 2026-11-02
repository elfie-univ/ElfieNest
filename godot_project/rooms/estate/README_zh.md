# 完整园区源码与功能回放

> [English](README.md)

`res://rooms/estate/estate.tscn` 通过 `rooms/nest.tscn` 加载唯一完整园区。
建筑、家具、基础网格和材质保留已提交基线，仅合入已确认的林间环路、回接支路、平滑地面分区、
沿路植物调整，以及九组保留灯具（E01–E02、R01–R07）。场景的 `source_sha256` 记录原桌面导出；
`integrated_model_sha256` 与 `instance_sidecar_sha256` 标识当前合入后的输入。

| 源资源 | 当前内容 |
| --- | --- |
| `ElfieNest-complete-final.glb` | 266,635,048 字节；在基线上选择性加入地形和灯具 |
| `ElfieNest-complete-final.instances.bin` | 134 组庭院实例、214,448 个实例；13,728,712 字节 |
| `estate_outdoor_lighting.scn` | 道路／广场引导、湖岸轮廓、四盏高杆灯（含广场边缘朝内照明的成对 6.5 米一体式单臂路灯及立体乳白灯罩，宽光束瞄准中心、交叠覆盖整个广场，以及一盏同款同尺寸的 6.5 米湖边单臂灯）、两盏复用环路款式的 1.17 米入口灯及 23 盏林间灯 |
| `estate_spatial.res` | 匹配当前模型的碰撞、活动边界、原生导航及楼梯连接 |

运行时加载离线空间资源，模型、实例或灯光输入不匹配时拒绝旧资源。
道路、广场、草地与林间小路连通，种植区、水体、设施和简化树干继续受保护；
移动边界不进入感知射线的碰撞掩码。
十扇实际门（原有八扇及中央两扇）共用接近打开、延时关闭、中途反向和占用体积防夹。
显式默认开门接口已保留；把该策略接到世界昼夜时段仍是本次迁移之外的待接线项。

Nest 提供本地民用时间：06–18 白天、18–24 上半夜、00–06 下半夜。
普通灯具与原模型自发光受统一开关控制，下半夜保留引导灯及按使用情况照明的策略。
表面接受实际灯光，不含已否决的固定暖色增亮项。正式监控的时间与视角独立选择；
预览不改变 Nest 时间或居民状态。

常规目录包含一个庭院视角、主楼四层及八组卧室／露台视角；正式监控再加入园区／林间
通行范围和环路视角。保留环绕、缩放、有限平移、当前视角复位及精灵跟随偏移。

完整园区与真实精灵的效果统一通过产品 `/monitor` 页面查看。
Developer Tools 的 `/nest/experiment` 页面继续保留，供隔离的 Nest Lab 实验使用；
其中的临时角色和模拟控制不操作正式居民。资产工作台继续使用 `/assets/design`。

独立动画巡检及机位、椅子、水面、碰撞、灯光评审页面已退役，旧查询参数不再选择评审模式。
Monitor 保留现有的调试时段预览与正常机位控制。

正式到达时序、叶片／光柱／穹顶灯光与寄身罩体位于 `rooms/estate/` 下的
`estate_platform_cycle.gd`、`estate_arrival_lighting.gd`、`estate_petal_charge.gd`、
`estate_event_effects.gd` 及相邻着色器。
`runtime/actor/adoption_arrival.gd` 负责物理到达路径，
`runtime/observer/resident_effects.gd` 将效果绑定到真实精灵状态。
领养只有到达；寄身时身体留在床上，不增加传送离开或声音。
骨骼动作源文件继续保存在 `characters/animation/`。
正式场景及效果不依赖 `runtime/lab`；仅明确进入精灵实验或 Nest Lab 模式时才加载 Lab 桥接。

离线创作使用仓库受控 Godot 入口：

```sh
bash scripts/quality/checks/godot_host.sh res://scripts/tools/bake_estate_lighting.gd
# 检查 build/estate-lighting-v4/estate_outdoor_lighting.scn 后发布到本目录。
bash scripts/quality/checks/godot_host.sh res://scripts/tools/bake_estate_spatial.gd
# 检查 build/estate_spatial/bake-report.json 后发布 estate_spatial.res 到本目录。
bash scripts/quality/checks/godot_host.sh res://scripts/test/test_estate_precompiled_spatial.gd
```

中间产物留在 `build/`；上述最终创作资源属于源资产。
Godot 导入缓存只保留本地并排除 Git。Web 产物仅由 `./developer.sh build-godot-web`
生成到 `build/components/godot-web/`。
