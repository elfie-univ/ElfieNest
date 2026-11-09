# 园区运行支持

> English: [`README.md`](README.md)

`nest/nest.tscn` 只加载 `nest/assembly/estate.tscn` 这一份显示总装。
建筑、家具、庭院场景逐层引用共享 GLB 原型。本目录保留碰撞、导航、语义、灯光、水景、
抵达和相机的共享脚本、shader 与烘焙后的 `estate_spatial.res`，不再保存第二个整园模型或实例边车。

`assembly/activity_regions.tres` 提供活动权限，`assembly/runtime-bindings.json`
提供逐摆位身份与灯光控制。编译后的无显示 authority 保留相同的碰撞几何、导航、
交互接触点和十扇可操作门，不加载显示网格。当地时间、灯光切换、水景动画和居民效果
继续使用现有所有者；拆分总装不创建第二个世界 authority。

修改正式资产或运行脚本后执行：

```sh
bash scripts/quality/checks/godot_host.sh res://tools/bake_estate_spatial.gd
# 检查 build/estate_spatial/bake-report.json 并验证候选。
# 将 estate_spatial.res 发布到本目录，runtime-inputs.json 同步到 assembly/。
bash scripts/quality/checks/godot_host.sh res://test/test_estate_precompiled_spatial.gd
./developer.sh build-godot-web
```

Web 与 Linux Dedicated 导出都会拒绝陈旧输入回执。Web 的物理 authority 包从同一份完整导出
派生，保留物理和角色资源，移除园区显示资源。`tools/bake_estate_lighting.gd` 仅把当前区域
灯具快照写入 `build/courtyard-lighting/`；修改灯光应编辑所属拆分场景。

通过 Nest Lab（`./developer.sh nest-lab`、`/nest/experiment`）查看资产及临时人物；产品
`/monitor` 观察真实居民。生成中间产物只写根 `build/`，Godot 导入缓存留在本地。
