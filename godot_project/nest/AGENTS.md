# Nest 资产目录与编辑规则

## 两条硬规则

1. **页面和文件双向一一对应。** 正式拆分目录内的每个 GLB、SCN、TSCN 有一个 ID、一个文件路径和
   一个菜单末级入口。「文件与引用」也指向这个条目。分组目录只负责导航，贴图、文件内网格和实例
   沿用所属资产条目。打包时双向核对菜单、文件和引用。
2. **原型唯一，逐层引用。** 每个几何原型只归一个 GLB。底层「详细部件」直接打开 GLB，
   SCN 持有引用、摆位、材质变体和行为，由对象组装到功能区、庭院和整园。同一 GLB 内的复用留在文件内部，
   跨文件复用由使用方引用唯一原型，树枝、树叶和路灯同样适用。

## 当前正式入口

- `res://nest/nest.tscn` 是唯一 Nest 入口。`nest.gd` 加载 `estate/estate.tscn`，其运行输入包括
  `estate/ElfieNest-complete-final.glb`、同名 `.instances.bin`、灯光场景、空间烘焙资源、脚本和 shader。
  当前修改正式场景时，沿这条引用链定位现役资源。
- `furniture/bedroom/` 和 `layouts/bedroom/bedroom.tscn` 是卧室组件试点，编辑规则见
  [卧室家具 AGENTS.md](furniture/bedroom/AGENTS.md)。整园入口当前仍加载完整园区。
- Nest Lab 的「单件资产」和「回拼对照 → 回拼」从 `res://nest/` 加载拆分资源。
  [asset-index.json](assembly/asset-index.json) 登记每个资产的菜单路径、文件和引用关系。
  模型、贴图、场景及渲染资源都在本目录。改文件路径或增减引用时同步更新索引。
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
├── estate/                       过渡期保留的合并版及其配套资源
├── furniture/                    家具、套装及室内和露台摆位
├── buildings/                    建筑原型和建筑总装
├── courtyard/                    庭院总装、四个功能区及其部件
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

Nest Lab 的「总组装」和「回拼对照 → 回拼」都读取 `assembly/estate.tscn`。
「原版 V044」从保留的 `estate/estate.tscn` 评估得到同一时段的静态对照。
并行验收期间，`nest.tscn` 的交互运行和发行导出使用合并版及其配套空间数据。

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
└── textures/                     家具引用的外置贴图
```

- `layouts/` 保存空间里的位置和朝向。主楼三层各一份，八个露台保留各自的布置。
  卧室只有一份完整布局，建筑总装以位置和朝向实例化八次，不再生成 M02–M08 的场景副本。
  四楼到达平台归建筑。
- `sets/` 保存套装内各件家具的相对摆位。引用多份原型的套装用 SCN，
  自包含的组合可直接用 GLB。只给某套装用的 GLB 随套装，露台独用部件随该露台布置。
  弧形书架灯光装配引用书架 GLB，并保存独立的灯光节点。
- `shared/` 按实际复用归档。一件家具可以是一份 GLB，同类原型也可同存一份库。
  桌面 A–D 和共用柜体同归 `bedroom-cabinet.glb`，由四个套装直接引用。家具套装菜单只保留
  卧室套装 A–D，不再增加桌柜 A–D 的局部 SCN 或桌面 GLB。
- Nest Lab 的「完整布置」和「家具套装」按用途导航。「家具与装饰」既能打开共享库，
  也能打开弧形书架等专用 GLB。每项指向所属目录中的同一个文件。

### 建筑

```text
buildings/
├── building-layout.scn           放置主楼及八个小屋，接入对应的家具布局
├── main/
│   └── central-building.glb      完整主楼结构、双扇入口、固定设施、四楼到达平台
├── pod/
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
│   ├── forest/
│   ├── waterside/
│   └── meadow/
├── parts/
│   ├── ground/
│   ├── forest/
│   ├── waterside/
│   ├── meadow/
│   └── shared/                  跨功能区复用的唯一原型
└── textures/                     庭院引用的外置贴图
```

「庭院」是外层分类。右侧第一级固定为总览、功能区、详细部件，第二级为区域，第三级为文件。
总览的「全庭院」只有「庭院总装（不带罩）」和「庭院总装（带罩）」，分别对应
`courtyard/overview/courtyard-all/courtyard-layout.scn` 与 `courtyard-covered.scn`。
功能区使用地面、森林、水榭、草原四个分区；详细部件另加「共享」，避免跨区资源重复归档。
下表路径相对于 `courtyard/`。

| 分区 | 功能区总装 | 详细部件 |
| --- | --- | --- |
| 地面 `ground` | `areas/ground/courtyard-ground.scn` | `parts/ground/` 下的 `shared-ground.glb`（地形、草坪、贴地道路及广场铺装）、`outdoor-lights.glb`（路灯原型）和 `courtyard-cover.glb`（庭院罩） |
| 森林 `forest` | `areas/forest/forest-layout.scn` | `parts/forest/tree-one.glb`（标志大树独有木结构） |
| 水榭 `waterside` | `areas/waterside/waterside-layout.scn` | `parts/waterside/` 下的 `lake.glb`、`fountain.glb`、`waterfall.glb` 和 `bench.glb` |
| 草原 `meadow` | `areas/meadow/meadow-layout.scn` | `parts/meadow/` 下的 `picnic.glb` 和 `swing.glb` |
| 共享 `shared` | 无独立功能区 | `parts/shared/` 下的 `plant-library.glb`、`forest-wood.glb`、`forest-foliage.glb` 和 `shore-stones.glb` |

对象子装配及专用依赖放在所属主场景的同名子目录，在对应分区的菜单中也有独立入口。
子装配归「功能区」，专用及共享 GLB 归「详细部件」。

- 不带罩总装持有四个功能区及其灯光环境；带罩总装引用它和 `parts/ground/courtyard-cover.glb`。
  整园回拼引用带罩总装，两种庭院总装的地面、植物、设施和灯光保持相同。
- 森林总装引用 `areas/forest/forest-layout/landmark-tree.scn`。打开后可分别查看标志大树木结构、
  树干与树枝、树叶与树冠三个 GLB 的引用。林间护栏端柱随森林总装，保存在同目录的
  `forest-trail-fixtures.glb`。
- 水榭总装拥有 `areas/waterside/waterside-layout/` 下的 `waterside-path.glb` 和 `water-lilies.glb`，
  岸石引用 `parts/shared/shore-stones.glb`。
  同目录内的 `fountain.scn` 和 `waterfall.scn` 各自引用对应的详细部件 GLB。

连续贴地道路、喷泉旁的连接石板和收边统一归地面铺装，路灯摆位归地面总装。
花草库按原型展示。同株的茎、叶、花瓣和花心从同一 GLB 成组预览，摆位与材质变体归使用方。
树干和树叶库各按类型展示一个代表，林区装配可引用库内对应的剪枝和树冠变体。
同一几何旋转后复用时，把旋转和颜色变体留在装配的摆位和材质数据里。

## 唯一拥有者与修改入口

- 详细部件只登记共享原型、可独立摆放或编辑的对象，以及需要单独验收的重要部件。
  单次使用的碎件留在所属组件。单 GLB 能完整表达对象时直接引用 GLB。
  共用贴图随 GLB 的引用管理。植物总装保留过滤、实例变换与空间分批。
- **改形状找原型，改位置找摆位。** 从 Nest Lab 的「文件与引用」沿引用找拥有者，
  再定位正式 `res://nest/` 路径。改路灯款式进入路灯原型，挪一盏路灯进入地面总装的对应实例。
  实例变体和可变状态在使用方修改。灯光策略、水流、交互、碰撞及导航沿场景引用定位对应脚本、
  shader 或烘焙输入。每个原始节点只有一个拥有者。
- **一个原型只编辑一份上游。** 已登记的 GLB 是形状源时改该 GLB。卧室试点以对应的
  `source/*.blend` 为形状源，GLB 与原生 SCN 按各自流程生成。派生预览和烘焙产物随源重建。
  重命名或移动时在同一变更里更新场景、贴图 URI、实例数据及索引引用。

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
