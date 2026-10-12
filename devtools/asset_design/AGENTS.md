# 房屋资产设计工作台

- 唯一页面为 `/assets/design`，唯一查看器为本目录 `web/viewer.html` 与
  `web/viewer.js`。沿用已确认的资产库布局和右侧完整控制栏。
- 房间、家具、露台设计任务只更新模型与 `build/asset_previews/catalog.json` 中的资产
  数据。不得复制查看器、另建模型专用 HTML、启动临时预览网站或改写界面。
  界面修改必须来自用户明确提出的界面需求；不能作为模型任务的附带改动。
- GLB、Blender、贴图、测量数据和参考图保留在原资产目录。几何与尺寸从对应真实
  模型或测量文件读取，不在页面中制造替代底板或复制建筑尺寸。
- `./developer.sh asset-design` 是独立启动入口；统一 Developer Tools 服务也挂载相同
  页面。它不构造 Elfie、Nest 实验、Godot Runtime 或生产服务，不访问生产数据。
- 测试位于 `test/devtools/asset_design/`，保护固定布局、单一查看器、资产切换和
  文件访问边界。不能为让检查通过而自动更新批准版的布局基准。
