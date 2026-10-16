# 房屋资产设计工作台

- 唯一页面为 `/assets/design`，唯一查看器为本目录 `web/viewer.html` 与
  `web/viewer.js`。沿用已确认的资产库布局和右侧完整控制栏。
- 房间、家具、露台设计任务只更新模型与 `devtools/asset_design/assets/catalog.json` 中的资产
  数据。不得复制查看器、另建模型专用 HTML、启动临时预览网站或改写界面。
  界面修改必须来自用户明确提出的界面需求；不能作为模型任务的附带改动。
- GLB、Blender、贴图、测量数据和参考图长期保存在本工具的 `assets/`，按对象与版本组织。几何与尺寸从对应真实
  模型或测量文件读取，不在页面中制造替代底板或复制建筑尺寸。
- `./developer.sh asset-design` 是独立启动入口。原实验服务和菜单不挂载该页面。
  它不构造 Elfie、Nest 实验、Godot Runtime 或生产服务，不访问生产数据。
- 测试位于 `test/devtools/asset_design/`，保护固定布局、单一查看器、资产切换和
  文件访问边界。不能为让检查通过而自动更新批准版的布局基准。

- 上方只选择模型、部件或效果图；对象与楼层只在预览区控制。不得恢复重复对象菜单
  或 M01 专用快捷按钮。切换对象保留有效楼层，视角不改变筛选与显示开关。
- 家具与建筑合并遵循 `docs/zh/developer/engineering/devtools.md` 的“资产合并原则”：
  按独立功能、运动和显隐边界合并，不按颜色分组；同时核验功能部件、绘制批次和
  三角面，保留动画部件及楼层标签。合并与减面分开验收。

- 设计资产唯一根为 `devtools/asset_design/assets/`，不得放进 Godot 源工程；最终交付导出另行执行。
  建筑归 `buildings/`，布置归 `layouts/`，家具归 `furniture/`，庭院归 `landscape/`。
  每个对象用 `source/model.glb`、`source/build.json` 保存编辑输入，用
  `versions/vNNN/model.glb`、`version.json`、`images/` 保存发布快照，参考图放对象的 `references/`。
- `catalog.json` 是加载与文件归属依据；`adoptions.json` 保存确认记录。生成或优化单个对象后，
  通过 `object_assets publish --object ... --image ... --reference ...` 登记，不能只把文件扔入目录。
  新版本不自动确认。`workspace scan` 核对登记文件与确认内容；缓存和清理备份只写根 `build/asset_design/`。
- 不直接运行迁移保留的历史生成脚本：它们仅作来源材料；后续生成器以当前对象的 source 目录为输入，
  临时输出写根 build，经过核验的编辑模型写回所属 source，再发布版本。
