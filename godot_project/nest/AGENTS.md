# Nest 资产目录与编辑规则

## 两条硬规则

1. **页面和文件双向一一对应。** 正式拆分目录内的每个 GLB、SCN、TSCN 有一个 ID、一个文件路径和
   一个菜单末级入口。「文件与引用」也指向这个条目。分组目录只负责导航，贴图、文件内网格和实例
   沿用所属资产条目。打包时双向核对菜单、文件和引用。
2. **原型唯一，逐层引用。** 每个几何原型只归一个 GLB。底层「详细部件」直接打开 GLB，
   SCN 持有引用、摆位、材质变体和行为，由对象组装到功能区、庭院和整园。同一 GLB 内的复用留在文件内部，
   跨文件复用由使用方引用唯一原型，树枝、树叶和路灯同样适用。

## 当前正式入口

- `res://nest/nest.tscn` 是唯一 Nest 入口，`nest.gd` 只加载 `assembly/estate.tscn`。
  正式运行、Nest Lab 整体场景与发行导出使用同一份拆分总装。
  `estate/` 保留物理、导航、交互、灯光、水景脚本、shader 与 `estate_spatial.res`，
  不是第二套模型来源。
- 正式卧室由 `furniture/layouts/bedroom/bedroom-layout.scn` 装入 A–D 套装，
  套装引用 `furniture/shared/bedroom/` 的原型。V044 卧室试点、工作稿和独立场景归
  [卧室创作试点](../tools/nest_authoring/bedroom-pilot/AGENTS.md)，其目录位于整园空间扫描和发行导出范围外。
- Nest Lab 的「单件资产」从 `res://nest/` 加载拆分资源。
  [asset-index.json](assembly/asset-index.json) 登记每个资产的菜单路径、文件和引用关系。
  模型、贴图、场景及渲染资源都在本目录。改文件路径或增减引用时同步更新索引。
- 拆分总装通过 `assembly/activity_regions.tres` 持有活动权限，活动面绑定当前 GLB 摆位；
  室外允许/禁止区域不是渲染几何的副本。`tools/export_split_activity.gd` 仅将导航输入和
  活动掩码导出到 `build/`，仅用于单独检查活动输入；正式运行使用 `tools/bake_estate_spatial.gd` 生成的完整空间快照。
- `asset_catalog.json` 保存 V044 原始提取绑定和指纹。旧拆分候选是迁入记录。
  浏览器预览从正式文件重新打包，`build/` 存放生成的网页包、对照快照和校验记录。

## 正式拆分目录

以本目录为根。家具、建筑、庭院各归一个目录。目录按组件实际落盘建立，每项使用稳定的资产 ID
和唯一的主文件路径。迁入、双版本验收和旧版清退按[资产迁入计划](ASSET_MIGRATION_PLAN.md)执行。

```text
nest/
├── AGENTS.md
├── ASSET_MIGRATION_PLAN.md
├── nest.tscn                     唯一 Nest 入口
├── nest.gd                       加载所选整园并绑定 Nest 行为
├── asset_catalog.json            V044 提取绑定
├── estate/                       共享运行脚本、shader 和空间快照
├── furniture/                    家具、套装及室内和露台摆位
├── buildings/                    建筑原型和建筑总装
├── courtyard/                    庭院总装、区域装配及其部件
├── assembly/
│   ├── estate.tscn               拆分版整园总装
│   ├── asset-index.json          Nest Lab 的菜单、文件及引用索引
│   ├── glb_placement.gd          从已导入 GLB 绑定网格和实例批次
│   └── render-resources/          装配场景引用的渲染资源
└── ui/                           Nest 观察界面资源
```

家具模型、套装和摆位同归 `furniture/`。建筑总装引用完整主楼、八个共享小屋实例，以及同一份
卧室布置的八个实例和各露台布置。拆分整园由 `assembly/estate.tscn` 引用建筑总装和带罩庭院总装。
园区级脚本和资源按实际职责归属，专用行为随所属组件。贴图按引用归到资产类内的 `textures/`，
真正跨类复用的贴图指定一个拥有者，各使用方引用该路径。

Nest Lab 的「总组装 → 全场景总组合」读取 `assembly/estate.tscn`。
页面只保留「整体场景」和「单件资产」，不再提供回拼对照和机位像素比较。
整园的交互与导出均使用这份总装，不保留第二个合并版入口。
`runtime-bindings.json` 按完整摆位路径保存语义与灯光控制；
`runtime-inputs.json` 记录空间快照对应的正式输入哈希。改动正式资源后先重新烘焙到根 `build/`，
检查并同步 `estate_spatial.res` 与输入回执，再执行正式 Web 或 Linux Dedicated 导出。
导出器拒绝陈旧输入，物理 authority 包保留同一份快照与回执，剔除显示资源。

## 回拼保真与比较

- 拆分 GLB 的导入设置使用 `meshes/force_disable_compression=true`，避免把已从 V044
  提取的坐标再次有损压缩。不要通过再次压缩共享几何消除比较差异。
- GLB 的 `emissiveFactor` 保存线性颜色；导入后的发光颜色与 V044 的实际材质核对。
  SCN 中持有的材质变体也要核对，不能只检查 GLB 的默认材质。
- glTF 无法表达的原生材质差值保存在所属 GLB 节点的 `extras.nest_materials`，由
  `glb_placement.gd.restore_materials()` 在装配绑定和单件预览中恢复。透明、深度、高光、
  纹理重复和发光运算都按原生设置核对；贴图的透明边缘处理和 mipmap 沿用对应 `.import`。
- 原版床品在各房间贴合后分别重算法线，极小坐标差也可能产生明显方向差。
  `bed-shared.glb` 内部的法线／切线变体共享原有 POSITION、INDEX、UV 等访问器；
  基节点 `extras.nest_normal_variants` 按房间 `estate_module` 和摆位 `v044_path` 选择变体节点。
  选择必须包含摆位，同一房间同一形状也可能有不同法线。内部变体不增加菜单项，
  `review_visible=false` 防止单件预览重复显示；仍只保留一份卧室布局与一份床品 GLB。
- 共用卧室布局的房间光照层由 `assembly/glb_placement.gd` 按所在 `estate_module`
  绑定，不能把 M01 的光照层直接复制到其余七间卧室。
- `tools/export_nest_comparison.gd` 只导出当前拆分版的评估快照至 `build/nest-comparison/`；
  `tools/compare_nest_snapshots.py` 可比较已保存的快照。历史 V044 比较不是运行入口。
- 静态画面不能替代动态水景、粒子、碰撞、导航、门和交互验收。

### 家具

```text
furniture/
├── layouts/                      一个房间、一层楼或一个露台的完整摆位
│   ├── main/                     central-layout-1.scn 至 central-layout-3.scn
│   ├── bedroom/
│   │   └── bedroom-layout.scn    唯一卧室布置，装入 A–D 四套家具
│   └── terraces/                 M01–M08 的露台场景及各自专用 GLB
├── sets/                         一套家具或一个功能点的组合
│   ├── bedroom/                  bedroom-set-a.scn 至 bedroom-set-d.scn
│   ├── main-floor-1/             客厅
│   ├── main-floor-2/             桌游、棋桌、游戏机、玩具、书架等
│   └── main-floor-3/             阅读、交谈、躺榻、书写等
├── shared/                       可被多套组合或多处摆位引用的文件
│   ├── bedroom/                  整床、转椅、卧室桌柜原型、台灯等
│   ├── main/                     座椅、桌几、植物、摆件、画框
│   └── terraces/                 座椅、矮桌、盆栽、地毯、内衬与灯槽
└── textures/                     家具引用的外置贴图，包括卧室正式套装与创作试点共用的贴图
```

- `layouts/` 保存空间里的位置和朝向。主楼三层各一份，八个露台保留各自的布置。
  卧室只有一份完整布局，建筑总装以位置和朝向实例化八次，不再生成 M02–M08 的场景副本。
  四楼到达平台归建筑。
- `sets/` 保存套装内各件家具的相对摆位。引用多份原型的套装用 SCN，
  自包含的组合可直接用 GLB。只给某套装用的 GLB 随套装，露台独用部件随该露台布置。
  弧形书架灯光装配引用书架 GLB，并保存独立的灯光节点。
- `shared/` 按实际复用归档。一件家具可以是一份 GLB，同类原型也可同存一份库。
  桌面 A–D 同归 `bedroom-desks.glb`，共用柜体、抽屉和灯片归 `bedroom-cabinet.glb`。
  四个卧室套装分别引用对应桌面和同一个柜子原型。
- Nest Lab 的「完整布置」和「家具套装」按用途导航。「家具与装饰」既能打开共享库，
  也能打开弧形书架等专用 GLB。每项指向所属目录中的同一个文件。
  完整家具在上一级显示为一条引用，具体零件在原型页查看。独立摆放的库内家具按原型列出，
  如同一客厅的茶几和边几。文件总大小对共享引用去重，各 GLB 显示自己的体积明细。
- 「完整布置」直接列出卧室和主楼一至三楼的完整布置；露台保留 M01–M08 分组。
  只省去这些总装的单项导航层，套装与具体部件的菜单分组保持原样。

### 建筑

```text
buildings/
├── building-layout.scn           放置主楼及八个小屋，接入对应的家具布局
├── main/
│   ├── source/central-building.blend   主楼的 Blender 工作稿
│   └── central-building.glb      完整主楼结构、双扇入口、固定设施、四楼到达平台
├── pod/
│   ├── source/pod-building.blend       小屋原型的 Blender 工作稿
│   └── pod-building.glb          八个小屋共用的建筑原型
└── textures/                     建筑引用的外置贴图
```

建筑菜单只列主楼、共享小屋、建筑总装配。门扇和门框属于主楼 GLB，入口可通过「文件与引用」
中的文件内部组件定位；门的移动状态由运行场景管理，不因此复制形状源。楼层家具和灯光归建筑总装。
八个小屋及卧室实例各自保存变换，卧室都引用同一份布局，露台按实际布置分别引用。
家具仍由 `furniture/` 持有。

### 庭院

```text
courtyard/
├── overview/courtyard-all/       不带罩与带罩的两个庭院总装 SCN
├── areas/
│   ├── ground/
│   ├── building/               中央建筑区绿化装配
│   ├── forest/
│   ├── waterside/
│   └── meadow/
├── parts/
│   ├── ground/
│   ├── forest/
│   ├── waterside/
│   ├── meadow/
│   └── shared/                  花草与石头原型
└── textures/                     庭院引用的外置贴图
```

「庭院」是外层分类。右侧第一级固定为总览、功能区、详细部件。
总览直接列出「庭院总装（不带罩）」和「庭院总装（带罩）」，分别对应
`courtyard/overview/courtyard-all/courtyard-layout.scn` 与 `courtyard-covered.scn`。
功能区直接列出地面与设施、建筑区绿化、水榭和草原总装；森林保留分组，内含森林区总装、标志大树及分叉树组、阔叶树组、针叶树组。
详细部件继续使用三级菜单：第二级为区域，第三级为文件，另加「共享」，只存放花草和石头原型。
树干、树枝、树叶与树冠由森林持有，其他区域引用同一份森林原型，不复制几何。
下表路径相对于 `courtyard/`。

| 分区 | 功能区总装 | 详细部件 |
| --- | --- | --- |
| 地面 `ground` | `areas/ground/courtyard-ground.scn` | `parts/ground/` 下的 `shared-ground.glb`（地形、草坪、道路、广场铺装、湖畔平台及湖岸外圈）、`outdoor-lights.glb`（路灯原型）和 `courtyard-cover.glb`（庭院罩） |
| 建筑区绿化 `building` | `areas/building/building-greenery.scn` | 原位引用共享花草库，不复制原型或公共地形 |
| 森林 `forest` | `areas/forest/forest-layout.scn` | `parts/forest/` 下的 `tree-one.glb`（分叉大树木结构）、`broadleaf-tree.glb`（阔叶树木结构）、`pine-tree.glb`（松树木结构、针叶与共享小枝）、`forest-foliage.glb`（共享阔叶与树冠）和 `forest-twigs.glb`（跨树类共享小枝） |
| 水榭 `waterside` | `areas/waterside/waterside-layout.scn` | `parts/waterside/` 下的 `lake.glb`（湖面与睡莲）、`fountain.glb`（喷泉、水道与瀑布）和 `bench.glb` |
| 草原 `meadow` | `areas/meadow/meadow-layout.scn` | `parts/meadow/` 下的 `picnic.glb` 和 `swing.glb` |
| 共享 `shared` | 无独立功能区 | `parts/shared/` 下的 `plant-library.glb`（花草）和 `shore-stones.glb`（石头） |

对象子装配及专用依赖放在所属主场景的同名子目录，在对应分区的菜单中也有独立入口。
子装配归「功能区」，专用及共享 GLB 归「详细部件」。

- 不带罩总装持有地面与设施、建筑区绿化、森林、水榭和草原装配及其灯光环境；带罩总装引用它和 `parts/ground/courtyard-cover.glb`。
  整园回拼引用带罩总装，两种庭院总装的地面、植物、设施和灯光保持相同。
- 森林、水榭、草原总装按地理范围引用 `shared-ground.glb` 内各自的地表片段及所属铺装、
  花草、石头与路灯摆位。中央范围、共用环路、外圈、连续土体的外壳和底面留在地面总装；
  这些片段合回一个连续土体，不增加分区内隔墙。功能区总装入口的 `focus` 保持为空，
  避免把完整总装误限制为某次新增的局部组件。
- 中央花草由建筑区绿化总装持有，公共地形与铺装仍归地面总装。低矮灌木按根部位置归区，
  同株茎叶一起迁移；复用相同原型的高处树冠组件保留在所属树木中。
- 森林总装引用 `forest-layout/` 下的 `branching-trees.scn`、`broadleaf-trees.scn` 和 `pine-trees.scn`。
  分叉树组引用 `landmark-tree.scn`，并保存另一棵大树的完整枝叶；标志大树仍可独立打开。
  专有木结构与针叶按树类归 GLB，跨类型阔叶和小枝保留唯一共享来源，不在多个 GLB 中复制。
  松树小枝按十二种形状通过 MultiMesh 复用，保留原位置、旋转及缩放。
  `tree_wood` 源元数据只标记原先参与树干碰撞的木结构，针叶与共享阔叶不参与该分类。主楼楼梯平台的两根扶手端柱归
  `buildings/main/central-building.glb`，复用原有栏杆立柱网格与材质；不设独立资产或森林菜单项。
- 水榭总装的湖水与睡莲引用同一份 `parts/waterside/lake.glb`，岸石引用
  `parts/shared/shore-stones.glb`。湖畔平台的基础和装饰铺面原型保留在地面 GLB，
  由水榭总装引用和摆位，不另设平台文件或菜单项。
  水榭总装直接保存喷泉、水道、瀑布的实例、粒子、计时器和动态材质，形状引用唯一的
  `parts/waterside/fountain.glb`；不再保留独立喷泉 SCN、睡莲 GLB、瀑布 GLB 或瀑布装配文件。

湖面 GLB 保存主湖水与两种睡莲原型，睡莲摆位仍由水榭装配持有。湖岸外圈及其下方的实体岸土归地面；
喷泉凸起的池沿及垫层、水道内的水、跌水与承接水面统一归喷泉 GLB，内部保留独立节点、材质和复用；
普通连接道路仍归地面，各组件按真实边界相接。

`shared-ground.glb` 内的地基、地表、草坪、缓坡和湖盆合为连续实体。
`COMPLETE Building garden island` 保存土石表面，`WholeLakeRibbon` 保存这个实体的岸灯外表面；
两者沿同一组边相接，共同构成一个封闭外壳。灯带表面不能再叠在一份同形岸体上，
也不恢复旧岸坡、草坪裙边、`GROUNDED soil contact collar` 或地下支撑板。
喷泉放在地面上，不在地面下另挖支撑坑。地下保留实体地基和湖盆必要的侧壁、底面。
石块必须封口；道路略高于实际地形，不能让草面穿入路面。修型后检查边的两侧方向、
连通性、重复面、道路净距、岸边和水道接触，再检查单件及装配效果。

连续贴地道路、喷泉旁的连接石板和收边统一归地面铺装，路灯摆位归地面总装。
散落景观石与岸石的原型统一归 `parts/shared/shore-stones.glb`；景观石的位置、旋转、
材质变体由地面总装持有。地形与铺装 GLB 不再包含散落石头，石头只在引用它们的总装中出现。
花草库按原型展示。同株的茎、叶、花瓣和花心从同一 GLB 成组预览，摆位与材质变体归使用方。
树类组件显示完整树组，形状原型预览展示代表，林区装配引用库内对应的剪枝、树冠与共享小枝变体。
同一几何旋转后复用时，把旋转和颜色变体留在装配的摆位和材质数据里。

## 唯一拥有者与修改入口

- **正式形状与渲染分块分开。** 地面的有效形状只存于所属 GLB，不能同时保存完整源网格和
  `GroundPatch_*` 派生副本。`shared-ground.glb` 拥有地形、草坪、道路、铺装、完整平台和湖岸外圈。
  已验收的地形修正、材质、法线和 UV 合回各自唯一来源；收口修正直接编辑该来源，不叠加覆盖副本。
- 需要分块的源节点通过 `extras.nest_render_partition` 声明格子尺寸和各表面的受光层。
  `assembly/glb_placement.gd` 根据三角面中心的 X/Z 位置生成 `RenderChunks`，保留原有三角面
  和原生顶点属性，不创建贴地覆盖平面。源网格改变时重建，源 GLB 重新导入后由加载或预览打包
  重新生成。分块节点没有场景 owner，不保存进 SCN，也不增加正式资产或菜单项。
- 单件 GLB 预览显示唯一形状源；装配中只绘制生成分块，源实例的渲染层为 0，生成节点记录其
  `source_geometry_path` 以支持文件引用和高亮。分块不是光源，不放进灯光控制层。
  原型实例批次、床品法线变体和喷泉动画模板分别保留各自必要数据，不能按隐藏状态一概删除。
  被替代的旧湖岸灯带已移除；休眠喷射模板不参与静态单件预览，真实喷嘴和灯片保留。
- 实例批次在上传前按变换格式、颜色和自定义参数开关核对数据步长与数量，保留原始实例缓冲。
  Compatibility 渲染会降低颜色和自定义参数的存储精度，不能用 GPU 读回值的逐字节一致性
  判断源数据是否完整，也不能因此中断后续组件绑定。

- 详细部件只登记共享原型、可独立摆放或编辑的对象，以及需要单独验收的重要部件。
  单次使用的碎件留在所属组件。单 GLB 能完整表达对象时直接引用 GLB。
  共用贴图随 GLB 的引用管理。植物总装保留过滤、实例变换与空间分批。
- **改形状找原型，改位置找摆位。** 从 Nest Lab 的「文件与引用」沿引用找拥有者，
  再定位正式 `res://nest/` 路径。改路灯款式进入路灯原型，挪一盏路灯进入地面总装的对应实例。
  实例变体和可变状态在使用方修改。灯光策略、水流、交互、碰撞及导航沿场景引用定位对应脚本、
  shader 或烘焙输入。每个原始节点只有一个拥有者。
- **一个原型只编辑一份上游。** 已登记的 GLB 是形状源时改该 GLB。主楼和小屋的 Blender
  工作稿从当前正式 GLB 重建；从 Blender 改形状时，先导出候选并核对材质、复用、摆位
  和 Godot 绑定，再将已验收的形状合入正式 GLB。装配、灯光和运行行为仍由正式场景持有。
  导出和重放用法见 [建筑编辑工具](../tools/nest_authoring/README.md)。
  重命名或移动时在同一变更里更新场景、贴图 URI、实例数据及索引引用。
- 每个 Blender `source/` 放空的 `.gdignore`。Godot 和 Nest Lab 的资产清单、导出检查
  均跳过该目录；创作源仍可纳入 Git。源稿、能重跑的脚本及需保留的旧版不得只存在
  `build/`；该目录只作为可再生的导出及临时工作区。

## 导出与迁入验收

- 冻结 V044 指纹后一次扫描模型、实例边车和动态依赖，编译明确的节点集合与引用，
  单次加载评估场景批量提取。几何和材质按内容指纹缓存，只重做输入变化的批次。
  `source` 只记录候选匹配。正式导出要求选择器、共享归属及动态绑定均已解析。
- 先核对文件与引用闭合、SCN 能从真实 GLB 绑定网格、跨 GLB 几何唯一、节点归属无遗漏无重复，再检查共享、材质变体、
  实例坐标和回拼画面。原型库预览每款只显示一次，引用数量按实例计算。未导出的入口明确标记其状态。
- 用 `./developer.sh nest-lab` 准备与正式源匹配的浏览器预览。已有服务可继续使用同一页面。
  Web 预览包、对照快照和校验记录生成在仓库根 `build/`。
  V044 原生 SCN 的静态回拼和正式 GLB 回拼分别验证。
  正式切换前还要核对灯光、碰撞、导航和动态绑定，按实际影响重烘焙。保留 V044、V045 备份。
  验收通过并确认切换后，由 `nest.tscn` 默认选择拆分总装。合并版的清退条件见迁入计划。
