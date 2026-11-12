# Nest 建筑源稿与重放工具

主楼的 Blender 工作稿在 `nest/buildings/main/source/`，八个小楼共用的工作稿在
`nest/buildings/pod/source/`（路径相对于 Godot 项目）。这两份工作稿从本次整理时
的正式 GLB 重建，带有内嵌贴图和原 GLB 的来源记录。Blender 会清理重面和退化面，
工作稿不代表旧建模工程的完整历史，也不保证能原样导回 Godot 专用材质和节点绑定。

- 改形状时打开所属 Blender 工作稿。先导出候选，核对复用部件、材质、摆位及 Godot
  元数据，再更新正式 GLB。正式 GLB 和装配场景是网页和运行时的输入。
- `source/.gdignore` 让 Godot 和打包检查跳过创作目录。工作稿可以随 Git 保存，
  Git 将它当二进制文件，不做文本差异。需要保留的工作稿不要放进 `build/`。
- 工具只生成候选或重放结果。修改位置、灯光、碰撞及导航时，按对应正式场景和空间
  烘焙流程更新。

从仓库根运行。下面用 `blender` 代表本机 Blender 5.2 可执行文件，Mac 可用
`/Applications/Blender.app/Contents/MacOS/Blender`。

```sh
blender --background --factory-startup --disable-autoexec --python-exit-code 7 \
  --python godot_project/tools/nest_authoring/building_blend.py \
  -- reconstruct main build/godot_assets/nest-authoring/main.blend

blender --background --factory-startup --disable-autoexec \
  godot_project/nest/buildings/main/source/central-building.blend --python-exit-code 7 \
  --python godot_project/tools/nest_authoring/building_blend.py \
  -- export-candidate main build/godot_assets/nest-authoring/main-review.glb
```

小楼用 `pod` 和 `pod-building.blend`。请选择新的输出文件，工具不会覆盖工作稿或正式 GLB。

`rebuild_main_wall.py` 重建主楼三楼的整圈内外墙面，用同一窗框轮廓开四个窗口，
并连接真实洞口侧壁。它从校验过的优化前 V044 模型测量圆形截面，保留原始屋顶连接面，
接回下层墙体；窗口区域随共享窗框使用统一曲面，上方平顺过渡回原屋顶轮廓。
它不拉扯旧窗洞顶点，不生成补片，也不改变门窗、楼板、楼梯、材质和实例绑定。
旧的逐顶点拟合工具已退役，备份只用于追溯。

修改前将 GLB、Blender 工作稿、装配、空间快照及输入收据复制到本工具的
`.archive/checkpoints/`，以 `manifest.json` 记录原路径和 SHA-256。该本机归档区不参与
Nest 运行输入扫描或 Web 导出。正式 Blender 工作稿仍位于主楼 `source/`。备份中的 `original-before-optimization.glb`
是冻结导出的原始形状参考，不是历史建模脚本；`before-previous-repair.glb` 提供保留的下层墙体。
工具必须在当前 checkout 的 Blender 工作稿中运行，输出目录必须是根 `build/` 下的新目录：

```sh
blender --background --disable-autoexec \
  godot_project/nest/buildings/main/source/central-building.blend --python-exit-code 7 \
  --python godot_project/tools/nest_authoring/rebuild_main_wall.py -- \
  --reference <检查点目录>/original-before-optimization.glb \
  --retained <检查点目录>/before-previous-repair.glb \
  --output build/main-wall-rebuild/new-candidate
```

候选应通过四窗轮廓、几何连通性、接缝方向和共享绑定检查，并在 Nest Lab 放大检查四窗。
同步正式 GLB 和 Blender 后，重烘焙空间快照并重新导出。恢复时按检查点清单核验哈希，
将选定备份复制回对应原路径；不要将有价值的回退输入只留在 `build/`。

用仓库锁定的前端依赖重放当时的存储压缩和几何优化：

```sh
node godot_project/tools/nest_authoring/building_replay/replay.mjs storage
node godot_project/tools/nest_authoring/building_replay/replay.mjs geometry
```

重放读取本机归档中的优化前 GLB、校验参数和历史报告，核对重放结果的 SHA-256。
几何重放还核对结果是否等于当前两份正式 GLB。重放的输出目录每次新建，旧 `build/`
内容和历史网页包不是重放输入。这里的历史重放固定针对当时的资产版本。

`.archive/` 是不进 Git 的本机归档，和正式创作目录分开。`inventory.json` 记录原路径和
哈希，相同内容只存一份。归档按哈希存储，没有场景或代码扩展名，避免被项目检查误读。
旧 V044 编辑候选、版本归档、旧模型与校验资料不参与正式预览或发行。

从清单找到原路径后，可恢复到新的临时位置：

```sh
.venv/bin/python3 godot_project/tools/nest_authoring/restore_archived_file.py \
  godot-asset-migration/exported-v044-native/authoring/pod-building.blend
```
